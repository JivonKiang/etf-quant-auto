# -*- coding: utf-8 -*-
"""ETF 量化交易自动化系统 · 每日主入口。

编排全流程：日志 -> 配置 -> 数据获取 -> (回测) -> (实盘信号/记录) -> 通知 -> 汇总。
每个阶段相互独立、异常可捕获，单点失败不中断整体（满足稳定性要求）。

用法：
    python run_daily.py              # 全流程（回测 + 实盘信号 + 通知）
    python run_daily.py --live-only  # 仅实盘信号
    python run_daily.py --backtest-only
    python run_daily.py --no-mail    # 不发邮件
"""
import os
import sys
import datetime

from core import config
from core.logger import get_logger, set_logger
from core import data_fetcher, backtest, executor, reporter, notifier, position_alert

log = get_logger()


def _run_backtest(nav_map, start_date):
    trades, equity, metrics = backtest.run_backtest(nav_map, config.CONFIG.strategy, start_date)
    reporter.save_backtest(metrics, equity, trades)
    reporter.save_trades(trades, tag="backtest")
    log.info("回测完成：胜率 %.1f%% / 均笔 %+.2f%% / 回撤 %.1f%% / 交易 %d 笔",
             metrics["win_rate"], metrics["avg_ret"], metrics["mdd"], metrics["trades"])
    return metrics


def _run_live():
    signals = executor.run_live()
    reporter.save_signals(signals)
    n_buy = sum(1 for s in signals if s["state"] == "BUY")
    log.info("实盘信号完成：共 %d 只标的，其中买入信号 %d 只", len(signals), n_buy)
    return signals


def _run_position_alert():
    alerts = position_alert.check_position_signals()
    if alerts:
        reporter.save_json(alerts, os.path.join(config.CONFIG.paths.signals_dir,
                                                f"position_alerts_{datetime.date.today().isoformat()}.json"))
        log.info("持仓提醒完成：%d 条（卖出 %d / 加仓 %d）",
                 len(alerts),
                 sum(1 for a in alerts if a["type"] == "SELL"),
                 sum(1 for a in alerts if a["type"] == "ADD"))
    else:
        log.info("持仓提醒完成：今日无买卖信号")
    return alerts


def main():
    args = set(sys.argv[1:])
    live_only = "--live-only" in args
    bt_only = "--backtest-only" in args
    no_mail = "--no-mail" in args

    log.info("=" * 60)
    log.info("ETF 量化自动化系统启动（%s）", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    log.info("运行时间配置 %s / 时区 %s",
             config.CONFIG.schedule.run_time, config.CONFIG.schedule.timezone)

    pool = config.CONFIG.strategy.pool.raw()
    metrics = None
    signals = []
    pos_alerts = []

    # 1) 数据获取（带重试，单只失败不中断）
    nav_map = data_fetcher.fetch_all_nav(pool)

    # 2) 回测（可选）
    if config.CONFIG.mode.backtest_enabled and not live_only:
        try:
            metrics = _run_backtest(nav_map, config.CONFIG.data_source.start_date)
        except Exception as e:
            log.exception("回测阶段异常（不影响实盘）：%s", e)

    # 3) 实盘信号（可选）
    if config.CONFIG.mode.live_enabled and not bt_only:
        try:
            signals = _run_live()
        except Exception as e:
            log.exception("实盘信号阶段异常：%s", e)

    # 4) 持仓买卖提醒（可选，随实盘一起跑）
    if config.CONFIG.mode.live_enabled and not bt_only:
        try:
            pos_alerts = _run_position_alert()
        except Exception as e:
            log.exception("持仓提醒阶段异常：%s", e)

    # 5) 汇总 + 通知
    report_text = reporter.render_markdown_report(signals, metrics)
    pos_report = position_alert.render_position_report(pos_alerts)
    if pos_report:
        report_text = report_text.rstrip() + "\n\n" + pos_report
    print("\n" + report_text)
    reporter.save_report(report_text)
    if not no_mail:
        notifier.send_email(f"📊 ETF 量化日报 {datetime.date.today()}", report_text)

    log.info("=" * 60)
    log.info("本次运行结束")
    return 0


if __name__ == "__main__":
    sys.exit(main())
