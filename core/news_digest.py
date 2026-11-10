# -*- coding: utf-8 -*-
"""零 LLM 信息面：东财 7×24 快讯 → 关键词过滤 → 落盘 JSON。

只做机械过滤与截断，不做任何 LLM 调用、不做情感判断，防幻觉。
"""
import datetime
import json
import os
import re

from . import config
from .data_fetcher import _http_get
from .logger import get_logger

log = get_logger()

FAST_URL = ("https://np-listapi.eastmoney.com/comm/web/getFastNewsList"
            "?client=web&biz=web_724&fastColumn=102&sortEnd=&pageSize={n}")

# 命中任一关键词才保留（机械规则，非 LLM）
KEYWORDS = ("ETF", "基金", "A股", "沪指", "深成指", "创业板", "降准", "降息",
            "北向", "央行", "证监会", "利好", "利空", "板块", "指数", "放量")


def fetch_fast_news(limit=50):
    """拉取东财 7×24 快讯最新 limit 条，返回 [{code,title,time,url}]。"""
    text = _http_get(FAST_URL.format(n=limit), encoding="utf-8")
    data = json.loads(text)
    items = (data.get("data") or {}).get("fastNewsList") or []
    out = []
    for it in items:
        raw = it.get("title") or it.get("summary") or ""
        title = re.sub(r"<[^>]+>", "", raw).strip()
        if not title:
            continue
        out.append({"code": it.get("code", ""),
                    "title": title[:80],
                    "time": it.get("showTime", ""),
                    "url": it.get("urlShowRelative", "")})
    return out


def digest():
    """生成今日信息面并落盘 data/news/<date>.json，返回 payload。"""
    try:
        news = fetch_fast_news()
    except Exception as e:
        log.warning("快讯拉取失败，信息面为空：%s", e)
        news = []
    hits = [n for n in news if any(k in n["title"] for k in KEYWORDS)][:20]
    today = datetime.date.today().isoformat()
    payload = {"date": today,
               "generated_at": datetime.datetime.now().strftime("%H:%M:%S"),
               "source": "eastmoney 7x24 fastnews",
               "llm_used": False,
               "total": len(news),
               "filtered": hits}
    news_dir = config.CONFIG.paths.news_dir
    os.makedirs(news_dir, exist_ok=True)
    path = os.path.join(news_dir, f"{today}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    log.info("信息面完成：快讯 %d 条，命中 %d 条 → %s", len(news), len(hits), path)
    return payload
