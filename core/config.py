# -*- coding: utf-8 -*-
"""配置加载：读取 config.json，合并默认值，并把相对路径解析为项目根目录下的绝对路径。

原则：所有数据路径以「项目根目录」为锚点（PROJECT_ROOT = core/ 的上级目录），
不依赖启动时的 cwd，也不使用机器相关的绝对路径，保证项目可迁移、易部署。
"""
import json
import os
from pathlib import Path

# 项目根目录 = 本文件(core/config.py)的上级目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_DEFAULTS = {
    "schedule": {"run_time": "14:45", "timezone": "Asia/Shanghai"},
    "paths": {
        "data_dir": "data",
        "nav_cache": "data/nav_cache",
        "signals_dir": "data/signals",
        "trades_dir": "data/trades",
        "log_dir": "data/logs",
    },
    "strategy": {
        "fast_ma": 10, "slow_ma": 30, "hold_days": 20, "min_hold": 7,
        "take_profit": 0.15, "macd_filter": True, "pool": {}, "etf_map": {},
    },
    "mode": {"backtest_enabled": True, "live_enabled": True},
    "data_source": {
        "fund_js": "http://fund.eastmoney.com/pingzhongdata/{code}.js",
        "realtime_url": "http://qt.gtimg.cn/q={codes}",
        "start_date": "2020-01-01",
    },
    "notify": {"email_enabled": True, "to": ""},
    "retry": {"max_attempts": 3, "backoff_seconds": 2},
}


def _deep_merge(base, override):
    """递归合并两个 dict，override 覆盖 base。"""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """配置对象：支持属性访问 cfg.strategy.fast_ma，也支持 cfg.get(...)。"""

    def __init__(self, data):
        object.__setattr__(self, "_data", data)

    def __getattr__(self, name):
        d = self.__dict__["_data"]
        if name in d:
            v = d[name]
            return Config(v) if isinstance(v, dict) else v
        raise AttributeError(name)

    def get(self, key, default=None):
        return self._data.get(key, default)

    def raw(self):
        return self._data


def _resolve_paths(cfg_data):
    """把 paths 里的相对路径解析为项目根目录下的绝对路径，并确保目录存在。"""
    p = cfg_data.get("paths", {})
    for key in ("data_dir", "nav_cache", "signals_dir", "trades_dir", "log_dir"):
        rel = p.get(key)
        if rel and not os.path.isabs(rel):
            abs_path = PROJECT_ROOT / rel
            p[key] = str(abs_path)
            abs_path.mkdir(parents=True, exist_ok=True)
    return cfg_data


def load_config(path=None):
    """加载配置。path 默认 config.json（位于项目根目录）。"""
    config_file = Path(path) if path else PROJECT_ROOT / "config.json"
    user = {}
    if config_file.exists():
        with open(config_file, encoding="utf-8") as f:
            user = json.load(f)
    merged = _deep_merge(_DEFAULTS, user)
    merged = _resolve_paths(merged)
    return Config(merged)


# 模块级单例，import 即用
CONFIG = load_config()
