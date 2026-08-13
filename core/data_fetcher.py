# -*- coding: utf-8 -*-
"""数据获取：场外基金净值（天天基金）+ 场内实时行情（腾讯）。

- 净值走本地缓存（data/nav_cache/{code}.json），命中缓存不再联网，保证离线/重跑不中断。
- 所有网络请求均带自动重试（见 utils.retry）。
"""
import json
import os
import re
import datetime
import urllib.request

from . import config
from .utils import retry, ensure_dir
from .logger import get_logger

log = get_logger()


def _http_get(url, timeout=30, encoding="utf-8"):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "http://fund.eastmoney.com/",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(encoding, "ignore")


@retry()
def fetch_nav(code, use_cache=True, force=False):
    """获取单只基金累计净值序列 [{date, nav}]，按日期升序。

    use_cache=True 且缓存存在时不联网（除非 force=True）。
    """
    cache = os.path.join(config.CONFIG.paths.nav_cache, f"{code}.json")
    if use_cache and not force and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            return json.load(f)

    url = config.CONFIG.data_source.fund_js.format(code=code)
    txt = _http_get(url)

    m = re.search(r"var Data_ACWorthTrend = (\[.*?\]);", txt, re.S)
    if m:
        raw = json.loads(m.group(1))
        arr = [{"date": datetime.datetime.fromtimestamp(x[0] / 1000, datetime.timezone.utc).date().isoformat(),
                "nav": x[1]} for x in raw]
    else:
        m = re.search(r"var Data_netWorthTrend = (\[.*?\]);", txt, re.S)
        if not m:
            raise ValueError(f"基金 {code} 数据源返回格式异常，未找到净值序列")
        raw = json.loads(m.group(1))
        arr = [{"date": datetime.datetime.fromtimestamp(x["x"] / 1000, datetime.timezone.utc).date().isoformat(),
                "nav": x["y"]} for x in raw]

    ensure_dir(os.path.dirname(cache))
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(arr, f, ensure_ascii=False)
    log.info("已缓存 %s 净值 %d 条（最新 %s）", code, len(arr), arr[-1]["date"] if arr else "-")
    return arr


@retry()
def fetch_realtime(etf_codes):
    """腾讯实时行情，返回 {场内code: {name, price, change_pct}}。etf_codes 如 ['sh510500']。"""
    if not etf_codes:
        return {}
    url = config.CONFIG.data_source.realtime_url.format(codes=",".join(etf_codes))
    txt = _http_get(url, timeout=10, encoding="gbk")
    result = {}
    for line in txt.strip().split(";"):
        line = line.strip()
        if not line:
            continue
        m = re.search(r'v_(\w+)="(.*?)"', line)
        if not m:
            continue
        code = m.group(1)
        p = m.group(2).split("~")
        if len(p) > 32:
            result[code] = {"name": p[1], "price": p[3], "change_pct": p[32]}
    return result


def fetch_all_nav(pool=None):
    """批量获取标的池净值，返回 {code: [{date,nav}]}。单只失败不影响其他标的。"""
    pool = pool or config.CONFIG.strategy.pool.raw()
    out = {}
    for code in pool:
        try:
            out[code] = fetch_nav(code)
        except Exception as e:
            log.error("获取 %s 净值失败，跳过：%s", code, e)
    return out
