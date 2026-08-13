# -*- coding: utf-8 -*-
"""策略执行（实盘侧）：场外基金无公开交易 API，实盘落地为「信号检测 + 记录 + 通知」。"""
import datetime

from . import config
from . import data_fetcher
from . import strategy
from .logger import get_logger

log = get_logger()


def run_live(today=None):
    """检测标的池每只基金的当前信号状态，返回信号列表。

    单只标的异常不影响整体（记录 ERROR 状态继续）。
    """
    pool = config.CONFIG.strategy.pool.raw()
    params = config.CONFIG.strategy
    today = today or datetime.date.today()

    signals = []
    for code, name in pool.items():
        try:
            arr = data_fetcher.fetch_nav(code)
            state, detail = strategy.signal_state(arr, params, today=today)
            signals.append({"code": code, "name": name, "state": state, **detail})
        except Exception as e:
            log.error("信号检测失败 %s(%s)：%s", name, code, e)
            signals.append({"code": code, "name": name, "state": "ERROR", "note": str(e)})
    return signals


def fetch_positions_realtime(positions):
    """持仓的场内 ETF 实时涨跌（用场外→场内映射代理当日走势）。"""
    etf_map = config.CONFIG.strategy.etf_map.raw()
    codes = list(dict.fromkeys(etf_map.get(p.get("code"), p.get("code")) for p in positions))
    try:
        return data_fetcher.fetch_realtime(codes)
    except Exception as e:
        log.warning("实时行情获取失败：%s", e)
        return {}
