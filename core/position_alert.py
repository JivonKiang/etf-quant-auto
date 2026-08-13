# -*- coding: utf-8 -*-
"""持仓买卖提醒：对用户实际持仓（data/positions.json）检测卖出/加仓信号。

卖出：止盈 +15% / 止损 -8% / 收盘跌破 MA20
加仓：突破 MA30 / 回踩 MA20 获支撑（MACD 红柱）
"""
import os
import json
import datetime

from . import config
from . import data_fetcher
from . import indicators as ind
from .logger import get_logger

log = get_logger()

POSITIONS_FILE = os.path.join(config.CONFIG.paths.data_dir, "positions.json")


def load_positions():
    if not os.path.exists(POSITIONS_FILE):
        return []
    try:
        with open(POSITIONS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def check_position_signals(today=None):
    """检测每只持仓的卖出/加仓信号，返回 alerts 列表。单只失败不中断。"""
    pos_cfg = config.CONFIG.position
    today = today or datetime.date.today()
    alerts = []

    for p in load_positions():
        code = p["code"]
        try:
            arr = data_fetcher.fetch_nav(code)
        except Exception as e:
            alerts.append({"code": code, "name": p["name"], "type": "ERROR", "reason": str(e)})
            continue

        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        m20 = ind.ma(nav, pos_cfg.break_ma)
        m30 = ind.ma(nav, pos_cfg.add_break_ma)
        hist = ind.macd_hist(nav)
        i = len(nav) - 1
        cur = nav[i]
        prev = nav[i - 1] if i > 0 else cur
        ret = cur / p["buy_nav"] - 1
        held = (today - datetime.date.fromisoformat(p["buy_date"])).days

        base = {"code": code, "name": p["name"], "ret": round(ret, 4),
                "held_days": held, "nav": round(cur, 4),
                "ma20": round(m20[i], 4) if m20[i] else None,
                "ma30": round(m30[i], 4) if m30[i] else None, "date": dates[i]}

        # 卖出信号
        if ret >= pos_cfg.take_profit:
            alerts.append({**base, "type": "SELL", "reason": "止盈 +15%"})
        elif ret <= pos_cfg.stop_loss:
            alerts.append({**base, "type": "SELL", "reason": "止损 -8%"})
        elif held >= pos_cfg.min_hold_days and m20[i] and m20[i - 1] \
                and prev > m20[i - 1] and cur < m20[i]:
            alerts.append({**base, "type": "SELL", "reason": "收盘跌破 MA20"})

        # 加仓信号
        if m30[i] and m30[i - 1] and prev <= m30[i - 1] and cur > m30[i]:
            alerts.append({**base, "type": "ADD", "reason": "突破 MA30 压力位"})
        elif m20[i] and hist[i] > 0 and 0.98 * m20[i] <= cur <= 1.02 * m20[i]:
            alerts.append({**base, "type": "ADD", "reason": "回踩 MA20 获支撑"})

    return alerts


def render_position_report(alerts):
    """生成持仓提醒的 Markdown 文本。"""
    if not alerts:
        return ""
    L = ["## 💼 持仓买卖提醒", ""]
    sells = [a for a in alerts if a["type"] == "SELL"]
    adds = [a for a in alerts if a["type"] == "ADD"]
    errs = [a for a in alerts if a["type"] == "ERROR"]
    if sells:
        L.append("### 🔴 卖出信号")
        for a in sells:
            L.append("- **%s**（%s）：%s，当前收益 %+.2f%%（净值 %.4f，持有 %d 天）" % (
                a["name"], a["code"], a["reason"], a["ret"] * 100, a["nav"], a["held_days"]))
        L.append("")
    if adds:
        L.append("### 🟢 加仓信号")
        for a in adds:
            L.append("- **%s**（%s）：%s，当前收益 %+.2f%%（净值 %.4f）" % (
                a["name"], a["code"], a["reason"], a["ret"] * 100, a["nav"]))
        L.append("")
    if errs:
        L.append("### ⚠️ 数据异常")
        for a in errs:
            L.append("- %s（%s）：%s" % (a["name"], a["code"], a["reason"]))
        L.append("")
    return "\n".join(L)
