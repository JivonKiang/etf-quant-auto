# -*- coding: utf-8 -*-
"""技术指标：MA / EMA / MACD 柱状图。纯标准库实现，无 pandas/numpy 依赖。"""


def ma(values, n):
    """简单移动平均，前 n-1 位为 None。"""
    out = [None] * len(values)
    s = 0.0
    for i, v in enumerate(values):
        s += v
        if i >= n:
            s -= values[i - n]
        if i >= n - 1:
            out[i] = s / n
    return out


def ema(values, n):
    """指数移动平均（以首值初始化）。"""
    k = 2.0 / (n + 1)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out


def macd_hist(values, fast=12, slow=26, signal=9):
    """MACD 柱状图 = 2*(DIF - DEA)，DIF=EMA(fast)-EMA(slow)，DEA=EMA(signal, DIF)。"""
    e_fast = ema(values, fast)
    e_slow = ema(values, slow)
    dif = [e_fast[i] - e_slow[i] for i in range(len(values))]
    dea = ema(dif, signal)
    return [2 * (dif[i] - dea[i]) for i in range(len(values))]
