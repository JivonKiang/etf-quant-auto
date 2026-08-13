# -*- coding: utf-8 -*-
"""策略逻辑：金叉 + MACD 过滤买入，固定持有 / 止盈卖出。

统一供「实盘信号检测」与「回测」两处使用，保证两者口径一致。
"""
import datetime

from . import indicators as ind


def _params_dict(params):
    """把 Config 子对象或 dict 归一为普通 dict。"""
    if hasattr(params, "raw"):
        return params.raw()
    return dict(params)


def signal_state(nav_series, params, today=None):
    """对单只标的判定当前状态，返回 (state, detail)。

    state: BUY(今日金叉) / HOLDING(持有中) / SELL_READY(满期或止盈) / WAIT(空仓观望)
    """
    p = _params_dict(params)
    fast, slow = p["fast_ma"], p["slow_ma"]
    hold_days = p["hold_days"]
    tp = p["take_profit"]
    macd = p.get("macd_filter", True)

    nav = [a["nav"] for a in nav_series]
    dates = [a["date"] for a in nav_series]
    mf = ind.ma(nav, fast)
    ms = ind.ma(nav, slow)
    hist = ind.macd_hist(nav)

    buy_idx = None
    for i in range(len(nav) - 1, slow - 1, -1):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
        if macd:
            cross = cross and hist[i] > 0
        if cross:
            buy_idx = i
            break

    if buy_idx is None:
        return "WAIT", {"note": "近期无金叉信号"}

    buy_date = dates[buy_idx]
    today = today or datetime.date.today()
    held = (today - datetime.date.fromisoformat(buy_date)).days
    latest_nav = nav[-1]
    detail = {
        "buy_date": buy_date, "held_days": held,
        "buy_nav": nav[buy_idx], "latest_nav": latest_nav,
        "ret": latest_nav / nav[buy_idx] - 1,
        "latest_date": dates[-1],
    }

    if buy_date == dates[-1]:
        return "BUY", detail
    if held < hold_days:
        # 止盈仅在持有期内判断（满期前）
        if tp and detail["ret"] >= tp:
            detail["reason"] = "止盈"
            return "SELL_READY", detail
        return "HOLDING", detail
    if held == hold_days:
        detail["reason"] = "满期"
        return "SELL_READY", detail
    return "WAIT", detail


def generate_trades(nav_series, params):
    """回测：返回交易列表 [{ret, buy_date, sell_date, hold, year}]。

    规则：金叉(+MACD)买入 -> 持有期间任一交易日满足「止盈 / 满期」即于当日卖出。
    """
    p = _params_dict(params)
    fast, slow = p["fast_ma"], p["slow_ma"]
    hold_days = p["hold_days"]
    tp = p["take_profit"]
    macd = p.get("macd_filter", True)

    nav = [a["nav"] for a in nav_series]
    dates = [a["date"] for a in nav_series]
    mf = ind.ma(nav, fast)
    ms = ind.ma(nav, slow)
    hist = ind.macd_hist(nav)

    trades = []
    pos = None
    for i in range(max(slow, 26), len(nav)):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
        if macd:
            cross = cross and hist[i] > 0

        if pos is None:
            if cross:
                pos = {"bn": nav[i], "bd": dates[i]}
        else:
            d0 = datetime.date.fromisoformat(pos["bd"])
            d1 = datetime.date.fromisoformat(dates[i])
            held = (d1 - d0).days
            ret = nav[i] / pos["bn"] - 1
            if (tp and ret >= tp) or held >= hold_days:
                trades.append({"ret": ret, "buy_date": pos["bd"], "sell_date": dates[i],
                               "hold": held, "year": pos["bd"][:4]})
                pos = None
    return trades
