# -*- coding: utf-8 -*-
"""模拟盘准入回测：候选 ETF 逐只独立回测（每只单独 5 万 account），胜率>50% 才入池。

防前视：与每日跑批共用 paper_broker.step()，信号用 T 日收盘价、成交按 T+1 开盘价。
指标 MA/MACD 只依赖 <=i 的数据（全量序列按位取值），无预热泄漏。
用法：
    python run_paper_backtest.py              # 用 config.json 的 start_date
    python run_paper_backtest.py 2023-01-01   # 指定起始日期
"""
import datetime
import json
import os
import sys

from core import config
from core import data_fetcher, paper_account, paper_broker
from core.logger import get_logger

log = get_logger()

# 候选池：胜率>50%（且平仓>=3笔）才入池
CANDIDATES = ["512660", "515030", "515790", "159992", "562500", "159755"]


def backtest_one(code, start_date):
    """单只独立回测：专属 5 万 account 重放历史 K 线，返回统计。"""
    kl_map = data_fetcher.fetch_all_kline([code])
    kl = kl_map.get(code)
    if not kl or len(kl["close"]) < 60:
        log.warning("%s 数据不足，跳过", code)
        return None
    dates = sorted(d for d in kl["index"].keys() if d >= start_date)
    if len(dates) < 60:
        log.warning("%s 回测区间数据不足（%d 日），跳过", code, len(dates))
        return None
    acct = paper_account.PaperAccount()
    for d in dates:
        paper_broker.step(acct, kl_map, d)
    sells = [t for t in acct.trades if t["side"] == "SELL"]
    total_closed = len(sells)
    win_rate = (sum(1 for t in sells if t.get("pnl_pct", 0) > 0)
                / total_closed * 100) if total_closed else 0.0
    final = acct.nav_daily[-1]["equity"] if acct.nav_daily else acct.initial_cash
    peak, mdd = 0.0, 0.0
    for row in acct.nav_daily:
        peak = max(peak, row["equity"])
        if peak > 0:
            mdd = min(mdd, row["equity"] / peak - 1)
    return {"code": code, "name": kl.get("name") or code,
            "win_rate": round(win_rate, 1),
            "trades": total_closed,
            "avg_ret": round(sum(t.get("pnl_pct", 0) for t in sells)
                             / total_closed * 100, 2) if total_closed else 0.0,
            "total_ret": round((final / acct.initial_cash - 1) * 100, 2),
            "mdd": round(mdd * 100, 1),
            "final_equity": round(final, 2),
            "pass": bool(win_rate > 50 and total_closed >= 3)}


def main():
    start = sys.argv[1] if len(sys.argv) > 1 else config.CONFIG.data_source.start_date
    log.info("=" * 60)
    log.info("模拟盘准入回测启动：候选 %d 只，起始 %s", len(CANDIDATES), start)
    results = []
    for code in CANDIDATES:
        try:
            m = backtest_one(code, start)
        except Exception as e:
            log.exception("%s 回测异常：%s", code, e)
            m = None
        if m:
            results.append(m)
            log.info("%s(%s)：胜率 %.1f%% / %d 笔 / 均笔 %+.2f%% / 总收益 %+.2f%% → %s",
                     m["code"], m["name"], m["win_rate"], m["trades"],
                     m["avg_ret"], m["total_ret"], "入池" if m["pass"] else "不入池")
    passed = [r["code"] for r in results if r["pass"]]
    payload = {"date": datetime.date.today().isoformat(),
               "start_date": start,
               "gate": "胜率>50% 且平仓>=3笔",
               "candidates": results,
               "passed": passed}
    path = os.path.join(config.CONFIG.paths.paper_dir, "backtest_gate.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("回测完成：入池 %d/%d → %s", len(passed), len(results), path)
    log.info("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
