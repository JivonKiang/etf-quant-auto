# -*- coding: utf-8 -*-
"""模拟盘撮合：T 日 15:05 跑批产出信号（T 日收盘价计算），成交按 T+1 开盘价撮合。

防前视偏差核心：signal_date < exec_date 的挂单才允许按 exec_date 开盘价成交；
当日收盘信号只入 pending，次日撮合。回测与每日跑批共用 step()，零偏差。
A 股 15:00 收盘，当日收盘价信号不可能当日成交，故必须顺延至次日开盘。
"""
import datetime

from . import config
from .indicators import ma, macd_hist
from .logger import get_logger
from .paper_account import buy_allowed

log = get_logger()


def _cfg():
    p = config.CONFIG.get("paper", {}) or {}
    return {
        "commission_rate": float(p.get("commission_rate", 0.00025)),
        "min_commission": float(p.get("min_commission", 5)),
        "slippage": float(p.get("slippage", 0.001)),
        "max_open_trades": int(p.get("max_open_trades", 2)),
        "position_pct": float(p.get("position_pct", 0.2)),
    }


def commission(amount, cfg=None):
    """佣金：万 2.5，最低 5 元（ETF 免印花税）。"""
    c = cfg or _cfg()
    return round(max(amount * c["commission_rate"], c["min_commission"]), 2)


def budget_for(account, cfg=None):
    """单标的预算 = 最近收盘总资产 × 单标的上限，且不超过可用现金。

    撮合时点（次日开盘）无当日收盘价，用最近一条收盘净值。
    """
    c = cfg or _cfg()
    base = account.nav_daily[-1]["equity"] if account.nav_daily else account.initial_cash
    return min(base * c["position_pct"], account.cash)


def shares_for(price, budget, cfg=None):
    """预算内可买股数（一手 100 股，含滑点与每笔佣金）。不足一手返回 0。"""
    c = cfg or _cfg()
    fill = price * (1 + c["slippage"])
    n = int(budget // fill) // 100 * 100
    while n >= 100:
        cost = n * fill + commission(n * fill, c)
        if cost <= budget:
            break
        n -= 100
    return n if n >= 100 else 0


def _indicators(kl, params=None):
    """计算 MA/MACD 指标并缓存到 kl["_indi"]（仅内存，不落盘）。"""
    if "_indi" in kl:
        return kl["_indi"]
    s = params or config.CONFIG.strategy
    indi = {"mf": ma(kl["close"], int(s.fast_ma)),
            "ms": ma(kl["close"], int(s.slow_ma)),
            "hist": macd_hist(kl["close"]) if s.macd_filter else None}
    kl["_indi"] = indi
    return indi


def _cross_at(indi, i):
    """i 日金叉：i-1 日 mf<=ms 且 i 日 mf>ms（只用 <=i 的数据，无前视）。"""
    mf, ms = indi["mf"], indi["ms"]
    if i < 1 or mf[i - 1] is None or ms[i - 1] is None or mf[i] is None or ms[i] is None:
        return False
    return mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]


def _fill_buy(account, code, kl, i, exec_date, c):
    """按 exec_date 开盘价撮合买入。成功返回 True。"""
    if code in account.positions:
        return False
    ok, why = buy_allowed(account, code, exec_date)
    if not ok:
        log.info("BUY %s 拒绝：%s", code, why)
        return False
    if len(account.positions) >= c["max_open_trades"]:
        return False
    open_price = kl["open"][i]
    budget = budget_for(account, c)
    n = shares_for(open_price, budget, c)
    if n < 100:
        return False
    fill = round(open_price * (1 + c["slippage"]), 3)
    amount = fill * n
    fee = commission(amount, c)
    account.open_position(code, n, fill, exec_date,
                          (kl.get("name") or code))
    account.cash -= fee
    account.trades.append({"code": code, "name": kl.get("name") or code, "side": "BUY",
                           "signal_date": "", "open_date": exec_date, "shares": n,
                           "open_price": fill, "amount": round(amount, 2),
                           "fee": fee, "reason": "金叉+MACD>0"})
    return True


def _fill_sell(account, code, kl, i, exec_date, c, reason=""):
    """按 exec_date 开盘价撮合卖出。成功返回 True（内部记 trades + 风控登记）。"""
    if code not in account.positions:
        return False
    fill = round(kl["open"][i] * (1 - c["slippage"]), 3)
    account.close_position(code, fill, exec_date, reason)
    return True


def step(account, kline_map, exec_date, params=None):
    """单日推进（回测与每日跑批共用核心）。

    exec_date 为撮合日。三段式：
    1. 撮合 pending：signal_date < exec_date 的挂单按 exec_date 开盘价成交；
       SELL 失败顺延（持仓必退出），BUY 失败作废（信号过期）。
    2. 收盘信号：按 exec_date 收盘价检查止盈/止损/满期/金叉，新信号入 pending。
    3. 记录净值（同日覆盖）。
    """
    c = _cfg()
    s = params or config.CONFIG.strategy
    take_profit = float(s.take_profit)
    stop_loss = float(config.CONFIG.get("position", {}).get("stop_loss", -0.08))
    hold_days = int(s.hold_days)

    sold_today = set()

    # ---- 1. 撮合 pending（防前视：signal_date < exec_date 才撮合） ----
    remain = []
    for od in account.pending_orders:
        if od["signal_date"] >= exec_date:
            remain.append(od)
            continue
        code = od["code"]
        kl = kline_map.get(code)
        i = kl["index"].get(exec_date) if kl else None
        if i is None:  # 当日无 K 线（停牌等），顺延
            remain.append(od)
            continue
        if od["side"] == "BUY":
            if not _fill_buy(account, code, kl, i, exec_date, c):
                log.info("BUY %s 作废（信号过期不追）", code)
        else:
            if _fill_sell(account, code, kl, i, exec_date, c, od["reason"]):
                sold_today.add(code)
    account.pending_orders = remain

    # ---- 2. 收盘信号（按 exec_date 收盘价，只入 pending 次日撮合） ----
    for code, kl in kline_map.items():
        i = kl["index"].get(exec_date)
        if i is None:
            continue
        close = kl["close"][i]
        indi = _indicators(kl, params)
        pos = account.positions.get(code)
        if pos:
            ret = close / pos["cost_price"] - 1
            i0 = kl["index"].get(pos["open_date"])
            held = (i - i0) if i0 is not None else hold_days  # 该标的自身交易日数
            if ret >= take_profit:
                account.add_pending(code, "SELL", exec_date, f"止盈 {ret:+.1%}")
            elif ret <= stop_loss:
                account.add_pending(code, "SELL", exec_date, f"止损 {ret:+.1%}")
            elif held >= hold_days:
                account.add_pending(code, "SELL", exec_date, f"持有满 {hold_days} 日")
        else:
            if code in sold_today:
                continue  # 当日卖出后不再反手
            if _cross_at(indi, i) and (indi["hist"] is None or indi["hist"][i] > 0):
                ok, why = buy_allowed(account, code, exec_date)
                if not ok:
                    log.info("信号 %s 拒绝：%s", code, why)
                    continue
                n_open = len(account.positions) + sum(
                    1 for o in account.pending_orders if o["side"] == "BUY")
                if n_open < c["max_open_trades"] and not account.has_pending(code):
                    account.add_pending(code, "BUY", exec_date, "金叉+MACD>0")

    # ---- 3. 记录净值 ----
    close_map = {code: kl["close"][kl["index"][exec_date]]
                 for code, kl in kline_map.items() if exec_date in kl["index"]}
    account.record_nav(exec_date, close_map)
