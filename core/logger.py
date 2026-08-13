# -*- coding: utf-8 -*-
"""日志：同时输出到控制台与文件（data/logs/YYYY-MM-DD.log）。

无人值守场景下日志是唯一可回溯的线索，务必落盘。
"""
import logging
import os
import sys
from datetime import date

_LOGGER = None


def get_logger(name="etf_quant", log_dir=None):
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER

    from . import config  # 延迟导入，避免循环依赖
    log_dir = log_dir or config.CONFIG.paths.log_dir
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{date.today().isoformat()}.log")

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if logger.handlers:  # 防止重复添加
        return logger

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    _LOGGER = logger
    return logger


def set_logger(logger):
    global _LOGGER
    _LOGGER = logger
