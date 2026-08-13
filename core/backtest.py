# -*- coding: utf-8 -*-
"""回测引擎：等权组合资金曲线 + 绩效指标。

口径：每只标的独立运行策略，空仓期计 0 收益；组合日收益 = 各标的日收益等权平均。
"""
import datetime
import statistics

from . import strategy
from . import config
from . import indicators as ind
from .logger import get_logger

log = get_logger()


def run_backtest(nav_map, params=None, start_date=None):
    """nav_map: {code: [{date,nav}]}；返回 (trades, equity, metrics)。"""
    params = params or config.CONFIG.strategy
    start_date = start_date or config.CONFIG.data_source.start_date

    fund_ret = {}
    all_dates = set()
    all_trades = []

    for code, arr in nav_map.items():
        arr = [a for a in arr if a["date"] >= start_date]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        trades = strategy.generate_trades(arr, params)
        for t in trades:
            t["code"] = code
        all_trades.extend(trades)

        # 复现持仓标记，构造日收益序列
        holding = [False] * len(nav)
        pos = None
        mf = ind.ma(nav, params.get("fast_ma"))
        ms = ind.ma(nav, params.get("slow_ma"))
        hist = ind.macd_hist(nav)
        slow = params.get("slow_ma")
        for i in range(max(slow, 26), len(nav)):
            if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
                continue
            cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i]
            if params.get("macd_filter", True):
                cross = cross and hist[i] > 0
            if pos is None and cross:
                pos = i
            if pos is not None:
                holding[i] = True
                d0 = datetime.date.fromisoformat(dates[pos])
                d1 = datetime.date.fromisoformat(dates[i])
                ret = nav[i] / nav[pos] - 1
                if (params.get("take_profit") and ret >= params.get("take_profit")) \
                        or (d1 - d0).days >= params.get("hold_days"):
                    pos = None
        ret = {}
        for i in range(1, len(nav)):
            ret[dates[i]] = (nav[i] / nav[i - 1] - 1) if holding[i] else 0.0
        fund_ret[code] = ret
        all_dates.update(dates)

    ds = sorted(all_dates)
    navv = 1.0
    equity = []
    daily = []
    for d in ds:
        rs = [fund_ret[c].get(d, 0.0) for c in nav_map]
        r = sum(rs) / len(rs)
        daily.append(r)
        navv *= (1 + r)
        equity.append({"date": d, "nav": round(navv, 4)})

    metrics = _calc_metrics(equity, daily, all_trades)
    return all_trades, equity, metrics


def _calc_metrics(equity, daily, trades):
    days = (datetime.date.fromisoformat(equity[-1]["date"])
            - datetime.date.fromisoformat(equity[0]["date"])).days
    cagr = (equity[-1]["nav"] / equity[0]["nav"]) ** (365 / days) - 1 if days > 0 else 0
    peak = 0.0
    mdd = 0.0
    for e in equity:
        peak = max(peak, e["nav"])
        mdd = min(mdd, e["nav"] / peak - 1)
    mdd = abs(mdd)
    sd = statistics.stdev(daily) if len(daily) > 1 else 0
    vol = sd * (252 ** 0.5)
    sharpe = (cagr - 0.02) / vol if vol > 0 else 0
    calmar = cagr / mdd if mdd > 0 else 0
    wins = [t["ret"] for t in trades if t["ret"] > 0]
    losses = [t["ret"] for t in trades if t["ret"] <= 0]
    pf = sum(wins) / abs(sum(losses)) if losses else 0
    win_rate = sum(1 for t in trades if t["ret"] > 0) / len(trades) if trades else 0
    avg = sum(t["ret"] for t in trades) / len(trades) if trades else 0

    by_year = {}
    for t in trades:
        by_year.setdefault(t["year"], []).append(t["ret"])
    year_win_rate = {y: sum(1 for r in rs if r > 0) / len(rs) for y, rs in sorted(by_year.items())}

    return {
        "cum_return": round((equity[-1]["nav"] - 1) * 100, 2),
        "cagr": round(cagr * 100, 2), "mdd": round(mdd * 100, 2),
        "sharpe": round(sharpe, 2), "calmar": round(calmar, 2),
        "profit_factor": round(pf, 2), "win_rate": round(win_rate * 100, 2),
        "avg_ret": round(avg * 100, 2), "trades": len(trades),
        "year_win_rate": {y: round(v * 100, 1) for y, v in year_win_rate.items()},
    }
