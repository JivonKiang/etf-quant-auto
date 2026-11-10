# -*- coding: utf-8 -*-
"""模拟盘账本：5 万虚拟资金，记录持仓/挂单/成交/净值，附风控保护（冷却/连亏暂停）。

设计参考 vnpy 官方 paper_account 模块：本地记账仿真，不对接真实下单。
状态持久化到 data/paper/account_state.json，同日净值覆盖写入防重跑重复累计。
"""
import datetime
import json
import os

from . import config
from .utils import ensure_dir
from .logger import get_logger

log = get_logger()

_STATE_FILE = "account_state.json"


def _protection_cfg():
    p = config.CONFIG.get("protections", {}) or {}
    return (int(p.get("cooldown_days", 5)),
            int(p.get("loss_pause_trades", 3)),
            int(p.get("loss_pause_days", 5)))


def record_close(account, code, pnl_pct, close_date):
    """平仓后登记风控状态：亏损→标的冷却+连亏计数；连亏达阈值→全局暂停买入。"""
    cooldown_days, loss_pause_trades, loss_pause_days = _protection_cfg()
    prot = account.protections
    if pnl_pct < 0:
        until = (datetime.date.fromisoformat(close_date)
                 + datetime.timedelta(days=cooldown_days)).isoformat()
        prot[f"cooldown_{code}"] = until
        prot["loss_streak"] = prot.get("loss_streak", 0) + 1
        if prot["loss_streak"] >= loss_pause_trades:
            prot["pause_until"] = (datetime.date.fromisoformat(close_date)
                                   + datetime.timedelta(days=loss_pause_days)).isoformat()
            prot["loss_streak"] = 0
            log.warning("连亏 %d 笔，暂停买入至 %s", loss_pause_trades, prot["pause_until"])
    else:
        prot["loss_streak"] = 0


def buy_allowed(account, code, today):
    """买入准入：(True, "") 或 (False, 原因)。先查全局暂停，再查标的冷却。"""
    prot = account.protections
    pause = prot.get("pause_until")
    if pause and today <= pause:
        return False, f"连亏暂停买入至 {pause}"
    cd = prot.get(f"cooldown_{code}")
    if cd and today <= cd:
        return False, f"{code} 冷却至 {cd}"
    return True, ""


class PaperAccount:
    """模拟盘账本。"""

    def __init__(self, initial_cash=None):
        p = config.CONFIG.get("paper", {}) or {}
        self.initial_cash = float(initial_cash or p.get("initial_cash", 50000))
        self.cash = self.initial_cash
        # {code: {shares, cost_price, open_date, name}}
        self.positions = {}
        # [{code, side, signal_date, reason}]
        self.pending_orders = []
        self.trades = []
        # [{date, cash, mv, equity}]
        self.nav_daily = []
        self.protections = {}

    # ---- 估值 ----
    def market_value(self, close_map=None):
        """持仓市值。缺价标的用成本价兜底。close_map: {code: close}"""
        total = 0.0
        for code, pos in self.positions.items():
            price = (close_map or {}).get(code) or pos["cost_price"]
            total += price * pos["shares"]
        return total

    def equity(self, close_map=None):
        return self.cash + self.market_value(close_map)

    def record_nav(self, date, close_map=None):
        """记录当日净值（同日覆盖，防重跑重复累计）。"""
        entry = {"date": date,
                 "cash": round(self.cash, 2),
                 "mv": round(self.market_value(close_map), 2),
                 "equity": round(self.equity(close_map), 2)}
        for i, d in enumerate(self.nav_daily):
            if d["date"] == date:
                self.nav_daily[i] = entry
                return entry
        self.nav_daily.append(entry)
        return entry

    # ---- 挂单 ----
    def add_pending(self, code, side, signal_date, reason=""):
        self.pending_orders.append({"code": code, "side": side,
                                    "signal_date": signal_date, "reason": reason})

    def has_pending(self, code):
        return any(o["code"] == code for o in self.pending_orders)

    # ---- 成交 ----
    def open_position(self, code, shares, price, open_date, name=""):
        """按成交价买入入账（扣现金，不记 trades，供撮合层组合使用）。"""
        cost = price * shares
        self.cash -= cost
        self.positions[code] = {"shares": shares, "cost_price": price,
                                "open_date": open_date, "name": name or code}

    def close_position(self, code, price, close_date, reason=""):
        """按成交价卖出入账（加现金，记 trades，并触发风控登记）。"""
        pos = self.positions.pop(code)
        proceeds = price * pos["shares"]
        self.cash += proceeds
        cost = pos["cost_price"] * pos["shares"]
        pnl = proceeds - cost
        pnl_pct = pnl / cost if cost else 0.0
        self.trades.append({"code": code, "name": pos["name"], "side": "SELL",
                            "open_date": pos["open_date"], "close_date": close_date,
                            "shares": pos["shares"], "open_price": pos["cost_price"],
                            "close_price": price, "pnl": round(pnl, 2),
                            "pnl_pct": round(pnl_pct, 4), "reason": reason})
        record_close(self, code, pnl_pct, close_date)
        return self.trades[-1]

    # ---- 持久化 ----
    def to_dict(self):
        return {"initial_cash": self.initial_cash, "cash": self.cash,
                "positions": self.positions, "pending_orders": self.pending_orders,
                "trades": self.trades, "nav_daily": self.nav_daily,
                "protections": self.protections}

    def save(self):
        path = os.path.join(config.CONFIG.paths.paper_dir, _STATE_FILE)
        ensure_dir(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls):
        path = os.path.join(config.CONFIG.paths.paper_dir, _STATE_FILE)
        acct = cls()
        if not os.path.exists(path):
            return acct
        try:
            with open(path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            log.warning("账本文件损坏，重置为初始状态")
            return acct
        acct.initial_cash = float(d.get("initial_cash", acct.initial_cash))
        acct.cash = float(d.get("cash", acct.initial_cash))
        acct.positions = d.get("positions", {})
        acct.pending_orders = d.get("pending_orders", [])
        acct.trades = d.get("trades", [])
        acct.nav_daily = d.get("nav_daily", [])
        acct.protections = d.get("protections", {})
        return acct
