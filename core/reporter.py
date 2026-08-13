# -*- coding: utf-8 -*-
"""结果记录：信号、交易、回测绩效、每日报告，全部落到 data/ 下相对路径。"""
import json
import os
import datetime

from . import config
from .utils import ensure_dir
from .logger import get_logger

log = get_logger()


def save_json(obj, path):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    return path


def save_signals(signals, today=None):
    """保存每日信号列表到 data/signals/{date}.json，同时更新 signals_latest.json。"""
    today = today or datetime.date.today().isoformat()
    path = os.path.join(config.CONFIG.paths.signals_dir, f"{today}.json")
    save_json(signals, path)
    latest = os.path.join(config.CONFIG.paths.signals_dir, "signals_latest.json")
    save_json(signals, latest)
    log.info("信号已保存：%s（%d 条）", path, len(signals))
    return path


def save_trades(trades, tag="backtest"):
    """保存交易明细到 data/trades/{tag}_{ts}.json。"""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(config.CONFIG.paths.trades_dir, f"{tag}_{ts}.json")
    save_json(trades, path)
    log.info("交易记录已保存：%s（%d 笔）", path, len(trades))
    return path


def save_backtest(metrics, equity, trades, today=None):
    """保存回测结果（绩效 + 资金曲线 + 交易）到 data/ 下。"""
    today = today or datetime.date.today().isoformat()
    result = {"date": today, "metrics": metrics, "equity": equity,
              "trades": trades, "strategy": config.CONFIG.strategy.raw()}
    path = os.path.join(config.CONFIG.paths.signals_dir, f"backtest_{today}.json")
    save_json(result, path)
    log.info("回测结果已保存：%s", path)
    return path


def save_report(text, today=None):
    """把每日报告文本落盘（供 agent-mail 自动化读取后发送）。"""
    today = today or datetime.date.today().isoformat()
    path = os.path.join(config.CONFIG.paths.signals_dir, f"report_{today}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    latest = os.path.join(config.CONFIG.paths.signals_dir, "report_latest.md")
    with open(latest, "w", encoding="utf-8") as f:
        f.write(text)
    log.info("报告已保存：%s", latest)
    return latest


def render_markdown_report(signals, metrics=None):
    """生成每日 Markdown 报告文本（供邮件/日志）。"""
    L = [f"# ETF 量化日报 — {datetime.date.today()}", ""]
    by_state = {}
    for s in signals:
        by_state.setdefault(s["state"], []).append(s)

    for state, title in (("BUY", "🟢 买入信号"), ("HOLDING", "🟡 持有中"),
                         ("SELL_READY", "🔵 到持有期（可卖出）")):
        if state in by_state:
            L += [f"## {title}", ""]
            for s in by_state[state]:
                ret = s.get("ret", 0) * 100
                L.append(f"- {s['name']}（{s['code']}）：持有第 {s.get('held_days', '-')} 天，收益 {ret:+.2f}%")
            L.append("")
    if not signals:
        L.append("今日无信号数据。")

    if metrics:
        L += ["## 回测绩效（累计）", ""]
        L.append("累计 %+.1f%% · 年化 %.1f%% · 回撤 %.1f%% · 夏普 %.2f · 卡玛 %.2f · 胜率 %.1f%% · 均笔 %+.2f%%" % (
            metrics["cum_return"], metrics["cagr"], metrics["mdd"], metrics["sharpe"],
            metrics["calmar"], metrics["win_rate"], metrics["avg_ret"]))
        L.append("")
    L.append("> 以上由 ETF 量化自动化系统自动生成，仅供研究参考，不构成投资建议。")
    return "\n".join(L)
