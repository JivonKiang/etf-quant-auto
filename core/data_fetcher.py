# -*- coding: utf-8 -*-
"""数据获取：场外基金净值（天天基金）+ ETF 日线 OHLC（东财）+ 场内实时行情（腾讯）。

- 净值/K线均走本地缓存（data/nav_cache/），命中缓存不再联网，保证离线/重跑不中断。
- K线增量拉取：只拉缓存最后日期之后的新增；重叠日价差 >0.1% 视为除权漂移自动全量重拉。
- 所有网络请求均带自动重试（见 utils.retry）。
"""
import json
import os
import re
import time
import datetime
import urllib.request

from . import config
from .utils import retry, ensure_dir
from .logger import get_logger

log = get_logger()

# 完整浏览器 UA + 全局请求节流（东财对裸 UA / 高频请求会直接断连）
_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "*/*",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
_MIN_INTERVAL = 0.6  # 相邻请求最小间隔（秒）
_last_ts = 0.0


def _http_get(url, timeout=30, encoding="utf-8"):
    global _last_ts
    gap = time.monotonic() - _last_ts
    if gap < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - gap)
    req = urllib.request.Request(url, headers={**_HEADERS,
        "Referer": "http://quote.eastmoney.com/"})
    _last_ts = time.monotonic()
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


# ==================== ETF 日线 OHLC（东财 push2his，前复权） ====================

KLINE_URL = ("https://push2his.eastmoney.com/api/qt/stock/kline/get"
             "?secid={secid}&klt=101&fqt=1&beg={beg}&end=20500101"
             "&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57")


def _secid(code):
    """东财 secid 规则：沪市（5/6/9 开头）前缀 1，深市前缀 0。"""
    return ("1." if code[0] in "569" else "0.") + code


def _parse_klines(klines):
    """解析东财 klines 列表「日期,开盘,收盘,最高,最低,成交量,成交额」。"""
    dates, o, c, h, l, v = [], [], [], [], [], []
    for line in klines:
        p = line.split(",")
        dates.append(p[0])
        o.append(float(p[1]))
        c.append(float(p[2]))
        h.append(float(p[3]))
        l.append(float(p[4]))
        v.append(float(p[5]))
    return {"dates": dates, "open": o, "close": c, "high": h, "low": l, "vol": v,
            "index": {d: i for i, d in enumerate(dates)}}


@retry()
def _fetch_kline_raw(secid, beg):
    """单次拉取 kline 原始数据。返回 {name, code, dates, open, close, high, low, vol, index}。"""
    data = json.loads(_http_get(KLINE_URL.format(secid=secid, beg=beg)))
    d = data.get("data") or {}
    if not d.get("klines"):
        raise ValueError(f"{secid} kline 返回空")
    return {"name": d.get("name") or secid,
            "code": d.get("code") or secid.split(".")[1],
            **_parse_klines(d["klines"])}


def fetch_kline(code, use_cache=True, force=False):
    """获取单只 ETF 前复权日线 OHLC，增量缓存（data/nav_cache/kline_{code}.json）。

    增量：命中缓存读最后日期作 beg，只拉新增（含重叠比对）；
    重叠日收盘价差 >0.1% 视为除权漂移，自动全量重拉；
    网络失败兜底返回旧缓存（如有）。
    返回 {name, code, dates, open, close, high, low, vol, index}。
    """
    cache = os.path.join(config.CONFIG.paths.nav_cache, f"kline_{code}.json")
    cached = None
    if use_cache and os.path.exists(cache):
        with open(cache, encoding="utf-8") as f:
            cached = json.load(f)
    beg = "19900101" if force or not cached else cached["dates"][-1]
    try:
        fresh = _fetch_kline_raw(_secid(code), beg)
        if cached and not force:
            drift = False
            for i, d in enumerate(fresh["dates"]):
                j = cached["index"].get(d)
                if j is not None and cached["close"][j] > 0 and \
                        abs(fresh["close"][i] - cached["close"][j]) / cached["close"][j] > 0.001:
                    drift = True
                    break
            if drift:  # 除权漂移：全量重拉
                fresh = _fetch_kline_raw(_secid(code), "19900101")
            else:  # 增量合并（fresh 已含重复的缓存末日，跳过已在缓存中的日期）
                start = sum(1 for d in fresh["dates"] if d in cached["index"])
                for k in ("dates", "open", "close", "high", "low", "vol"):
                    cached[k].extend(fresh[k][start:])
                cached["index"] = {d: i for i, d in enumerate(cached["dates"])}
                cached["name"] = fresh["name"]
                fresh = cached
    except Exception as e:
        if cached:
            log.error("获取 %s kline 失败，用旧缓存兜底：%s", code, e)
            return cached
        raise
    ensure_dir(os.path.dirname(cache))
    with open(cache, "w", encoding="utf-8") as f:
        json.dump(fresh, f, ensure_ascii=False)
    log.info("已缓存 %s kline %d 条（最新 %s，%s）",
             code, len(fresh["dates"]),
             fresh["dates"][-1] if fresh["dates"] else "-", fresh["name"])
    return fresh


def fetch_all_kline(pool=None):
    """批量获取标的池日线 OHLC，返回 {code: kline}。单只失败不影响其他标的。"""
    pool = pool or config.CONFIG.strategy.pool.raw()
    out = {}
    for code in pool:
        try:
            out[code] = fetch_kline(code)
        except Exception as e:
            log.error("获取 %s kline 失败，跳过：%s", code, e)
    return out
