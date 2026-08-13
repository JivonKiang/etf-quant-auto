# -*- coding: utf-8 -*-
"""通用工具：自动重试 + 目录确保。

稳定性要求：任何单次网络/IO 异常都不应中断整日任务，这里提供带退避的重试装饰器。
"""
import time
import functools
import os

from . import config


def retry(max_attempts=None, backoff=None, exceptions=(Exception,), logger=None):
    """重试装饰器：失败后按 backoff 秒退避重试，直到 max_attempts 次。

    用法：
        @retry(max_attempts=3, backoff=2)
        def fetch(...): ...
    """
    max_attempts = max_attempts if max_attempts is not None else config.CONFIG.retry.max_attempts
    backoff = backoff if backoff is not None else config.CONFIG.retry.backoff_seconds

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            while True:
                attempt += 1
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt >= max_attempts:
                        if logger:
                            logger.error("%s 重试 %d 次后仍失败: %s", fn.__name__, attempt, e)
                        raise
                    wait = backoff * (2 ** (attempt - 1))  # 指数退避
                    if logger:
                        logger.warning("%s 第 %d 次失败(%s)，%.0fs 后重试",
                                       fn.__name__, attempt, e, wait)
                    time.sleep(wait)
        return wrapper
    return decorator


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
