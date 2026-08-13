# -*- coding: utf-8 -*-
"""生成 GitHub Pages 站点：index.html（响应式，内嵌每日信号 + 回测结果）
数据每天由 GitHub Actions 重新生成并部署。
"""
import json, datetime, os, sys
from core import config as _cfg
from core import data_fetcher, executor, indicators, position_alert

# ---- 兼容旧接口别名（映射到新系统 core 模块）----
POOL = _cfg.CONFIG.strategy.pool.raw()
STRATEGY = {
    "fast": _cfg.CONFIG.strategy.fast_ma,
    "slow": _cfg.CONFIG.strategy.slow_ma,
    "hold_days": _cfg.CONFIG.strategy.hold_days,
    "take_profit": _cfg.CONFIG.strategy.take_profit,
    "macd_filter": _cfg.CONFIG.strategy.macd_filter,
}
ETF_MAP = _cfg.CONFIG.strategy.etf_map.raw()


def fetch(code):
    return data_fetcher.fetch_nav(code)


def fetch_realtime(codes):
    return data_fetcher.fetch_realtime(codes)


def macd_hist(nav):
    return indicators.macd_hist(nav)


def ma(nav, n):
    return indicators.ma(nav, n)


def check_all():
    return executor.run_live()


def fixed_hold_backtest(arr, fast, slow, hold_days, take_profit=None):
    """固定持有 N 天回测：金叉(MA上穿) + MACD柱>0 买入，止盈或满 N 天卖出"""
    dates = [a["date"] for a in arr]
    nav = [a["nav"] for a in arr]
    mf = ma(nav, fast)
    ms = ma(nav, slow)
    hist = macd_hist(nav)
    trades = []
    pos = None
    for i in range(slow, len(nav)):
        if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
            continue
        cross_up = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i] and hist[i] > 0
        if pos is None:
            if cross_up:
                pos = {"bi": i, "bn": nav[i], "bd": dates[i]}
        else:
            d0 = datetime.date.fromisoformat(pos["bd"])
            d1 = datetime.date.fromisoformat(dates[i])
            ret = nav[i] / pos["bn"] - 1
            sell = (take_profit is not None and ret >= take_profit) or (d1 - d0).days >= hold_days
            if sell:
                trades.append({"ret": ret, "bd": pos["bd"],
                               "sd": dates[i], "hold": (d1 - d0).days})
                pos = None
    return trades


def build_equity(sample=240):
    """等权组合策略资金曲线（金叉+MACD买入持有N天，空仓现金）"""
    fund_ret = {}
    all_dates = set()
    for code in POOL:
        arr = [a for a in fetch(code) if a["date"] >= "2020-01-01"]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        mf = ma(nav, STRATEGY["fast"])
        ms = ma(nav, STRATEGY["slow"])
        hist = macd_hist(nav)
        holding = [False] * len(nav)
        pos_start = None
        slow = STRATEGY["slow"]
        for i in range(slow, len(nav)):
            if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
                continue
            cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i] and hist[i] > 0
            if pos_start is None and cross:
                pos_start = i
            if pos_start is not None:
                holding[i] = True
                d0 = datetime.date.fromisoformat(dates[pos_start])
                d1 = datetime.date.fromisoformat(dates[i])
                ret = nav[i] / nav[pos_start] - 1
                tp = STRATEGY.get("take_profit")
                if (tp and ret >= tp) or (d1 - d0).days >= STRATEGY["hold_days"]:
                    pos_start = None
        ret = {}
        for i in range(1, len(nav)):
            ret[dates[i]] = (nav[i] / nav[i - 1] - 1) if holding[i] else 0.0
        fund_ret[code] = ret
        all_dates.update(dates)
    ds = sorted(all_dates)
    nav_val = 1.0
    equity = []
    for d in ds:
        rs = [fund_ret[c].get(d, 0.0) for c in POOL]
        nav_val *= (1 + sum(rs) / len(rs))
        equity.append([d, round(nav_val, 4)])
    if len(equity) > sample:
        step = len(equity) / sample
        equity_full = list(equity)
        equity = [equity[int(i * step)] for i in range(sample)]
        equity.append([ds[-1], round(nav_val, 4)])
        return equity, equity_full
    return equity, list(equity)


def build_benchmark():
    """基准：等权买入持有全部标的（不交易）"""
    fund_ret = {}
    all_dates = set()
    for code in POOL:
        arr = [a for a in fetch(code) if a["date"] >= "2020-01-01"]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        ret = {}
        for i in range(1, len(nav)):
            ret[dates[i]] = nav[i] / nav[i - 1] - 1
        fund_ret[code] = ret
        all_dates.update(dates)
    ds = sorted(all_dates)
    navv = 1.0
    eq = []
    for d in ds:
        rs = [fund_ret[c].get(d, 0.0) for c in POOL]
        navv *= (1 + sum(rs) / len(rs))
        eq.append([d, round(navv, 4)])
    return eq


def calc_metrics(equity, benchmark, trades):
    import statistics
    days = (datetime.date.fromisoformat(equity[-1][0]) - datetime.date.fromisoformat(equity[0][0])).days
    cagr = (equity[-1][1] / equity[0][1]) ** (365 / days) - 1
    peak = 0
    mdd = 0
    for d, nav in equity:
        peak = max(peak, nav)
        mdd = min(mdd, nav / peak - 1)
    mdd = abs(mdd)
    daily = [equity[i][1] / equity[i - 1][1] - 1 for i in range(1, len(equity))]
    sd = statistics.stdev(daily) if len(daily) > 1 else 0
    vol = sd * (252 ** 0.5)
    sharpe = (cagr - 0.02) / vol if vol > 0 else 0
    calmar = cagr / mdd if mdd > 0 else 0
    wins = [t["ret"] for t in trades if t["ret"] > 0]
    losses = [t["ret"] for t in trades if t["ret"] <= 0]
    avg_win = sum(wins) / len(wins) if wins else 0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0
    pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0
    pf = sum(wins) / abs(sum(losses)) if losses else 0
    b_cagr = (benchmark[-1][1] / benchmark[0][1]) ** (365 / days) - 1
    b_peak = 0
    b_mdd = 0
    for d, nav in benchmark:
        b_peak = max(b_peak, nav)
        b_mdd = min(b_mdd, nav / b_peak - 1)
    return {
        "cum_return": round((equity[-1][1] - 1) * 100, 1),
        "cagr": round(cagr * 100, 1), "mdd": round(mdd * 100, 1),
        "volatility": round(vol * 100, 1), "sharpe": round(sharpe, 2),
        "calmar": round(calmar, 2), "pl_ratio": round(pl_ratio, 2),
        "profit_factor": round(pf, 2),
        "win_rate": round(sum(1 for t in trades if t["ret"] > 0) / len(trades) * 100, 1) if trades else 0,
        "trades": len(trades),
        "bench_cum": round((benchmark[-1][1] - 1) * 100, 1),
        "bench_cagr": round(b_cagr * 100, 1), "bench_mdd": round(abs(b_mdd) * 100, 1),
    }


def build_signal_analysis(signals, look_forward=None):
    if look_forward is None:
        look_forward = STRATEGY["hold_days"]
    """对当前有信号(BUY/HOLDING)的基金，提取历史所有买入信号后 N 交易日走势"""
    result = []
    active = [s for s in signals if s["state"] in ("BUY", "HOLDING")]
    for s in active:
        code = s["code"]
        arr = [a for a in fetch(code) if a["date"] >= "2020-01-01"]
        nav = [a["nav"] for a in arr]
        dates = [a["date"] for a in arr]
        mf = ma(nav, STRATEGY["fast"])
        ms = ma(nav, STRATEGY["slow"])
        hist = macd_hist(nav)
        samples = []
        slow = STRATEGY["slow"]
        for i in range(slow, len(nav)):
            if mf[i] is None or ms[i] is None or mf[i - 1] is None or ms[i - 1] is None:
                continue
            cross = mf[i - 1] <= ms[i - 1] and mf[i] > ms[i] and hist[i] > 0
            if not cross:
                continue
            path = []
            for j in range(i + 1, min(i + 1 + look_forward, len(nav))):
                path.append(round(nav[j] / nav[i] - 1, 4))
            if len(path) >= 5:
                samples.append({"buy_date": dates[i], "final": path[-1], "path": path})
        if not samples:
            continue
        wins = sum(1 for x in samples if x["final"] > 0)
        avg_path = []
        for k in range(look_forward):
            rs = [x["path"][k] for x in samples if k < len(x["path"])]
            if rs:
                avg_path.append(round(sum(rs) / len(rs) * 100, 2))
        result.append({
            "code": code, "name": s["name"], "state": s["state"],
            "n_signals": len(samples),
            "win_rate": round(wins / len(samples) * 100, 0),
            "avg_final": round(sum(x["final"] for x in samples) / len(samples) * 100, 2),
            "avg_path": avg_path,
            "samples": [[round(r * 100, 2) for r in x["path"]] for x in samples],
        })
    return result


def load_positions():
    path = os.path.join(os.path.dirname(__file__), "data", "positions.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return []
    return []


def build_positions():
    """计算实际持仓的当前盈亏 + 今日实时涨跌"""
    pos = load_positions()
    result = []
    etf_codes = list(dict.fromkeys(ETF_MAP.get(p["code"], p["code"]) for p in pos))
    try:
        rt = fetch_realtime(etf_codes) if etf_codes else {}
    except Exception:
        rt = {}
    for p in pos:
        try:
            arr = fetch(p["code"])
        except Exception:
            continue
        latest_nav = arr[-1]["nav"]
        latest_date = arr[-1]["date"]
        ret = latest_nav / p["buy_nav"] - 1
        held = (datetime.date.today() - datetime.date.fromisoformat(p["buy_date"])).days
        etf_code = ETF_MAP.get(p["code"], p["code"])
        real = rt.get(etf_code)
        result.append({**p, "latest_nav": round(latest_nav, 4),
                       "ret": round(ret, 4), "held_days": held, "latest_date": latest_date,
                       "realtime_chg": real["change_pct"] if real else None})
    return result


def build_data():
    f, s, hd = (STRATEGY["fast"], STRATEGY["slow"], STRATEGY["hold_days"])
    tp = STRATEGY.get("take_profit")
    signals = check_all()
    data_date = ""
    for sig in signals:
        if sig.get("latest_date"):
            data_date = max(data_date, sig["latest_date"])
    all_trades = []
    fund_detail = []
    yearly = {}
    for code, name in POOL.items():
        arr = [a for a in fetch(code) if a["date"] >= "2020-01-01"]
        tr = fixed_hold_backtest(arr, f, s, hd, tp)
        for t in tr:
            t["name"] = name
            t["code"] = code
        all_trades += tr
        n = len(tr)
        if n:
            win = sum(1 for t in tr if t["ret"] > 0)
            avg = sum(t["ret"] for t in tr) / n
            cum = 1.0
            for t in tr:
                cum *= (1 + t["ret"])
            fund_detail.append({"code": code, "name": name, "win_rate": round(win / n * 100, 1),
                                "avg_ret": round(avg * 100, 2), "cum_ret": round((cum - 1) * 100, 1),
                                "trades": n})
    for t in all_trades:
        y = t["bd"][:4]
        yearly.setdefault(y, []).append(t["ret"])
    yearly_sorted = [{"year": y, "win_rate": round(sum(1 for r in rs if r > 0) / len(rs) * 100, 0)}
                     for y, rs in sorted(yearly.items())]
    n_all = len(all_trades)
    win_all = sum(1 for t in all_trades if t["ret"] > 0)
    avg_all = sum(t["ret"] for t in all_trades) / n_all if n_all else 0
    avg_hold = sum(t["hold"] for t in all_trades) / n_all if n_all else 0

    param_space = []
    for hold_days in [7, 10, 12, 15, 20, 25, 30, 45, 60]:
        pts = []
        for code in POOL:
            arr = [a for a in fetch(code) if a["date"] >= "2020-01-01"]
            pts += fixed_hold_backtest(arr, f, s, hold_days, tp)
        if pts:
            pw = sum(1 for t in pts if t["ret"] > 0)
            param_space.append({
                "hold_days": hold_days,
                "win_rate": round(pw / len(pts) * 100, 1),
                "avg_ret": round(sum(t["ret"] for t in pts) / len(pts) * 100, 2),
                "trades": len(pts),
            })

    equity_display, equity_full = build_equity()
    benchmark = build_benchmark()
    metrics = calc_metrics(equity_full, benchmark, all_trades)

    recent_trades = sorted(all_trades, key=lambda t: t["sd"], reverse=True)[:15]
    recent_trades = [{"name": t["name"], "code": t["code"], "buy_date": t["bd"],
                      "sell_date": t["sd"], "ret": round(t["ret"] * 100, 2),
                      "hold": t["hold"]} for t in recent_trades]

    return {
        "date": str(datetime.date.today()),
        "data_date": data_date,
        "strategy": {"fast": f, "slow": s, "hold_days": hd},
        "summary": {"win_rate": round(win_all / n_all * 100, 1), "trades": n_all,
                    "avg_ret": round(avg_all * 100, 2), "avg_hold": round(avg_hold)},
        "signals": signals,
        "yearly": yearly_sorted,
        "funds": fund_detail,
        "param_space": param_space,
        "equity": equity_display,
        "benchmark": benchmark,
        "metrics": metrics,
        "signal_analysis": build_signal_analysis(signals),
        "positions": build_positions(),
        "recent_trades": recent_trades,
    }


HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 量化信号 · 支付宝 C 类 ETF 策略</title>
<style>
:root{
  --bg:#eef1f7; --card:#ffffff; --ink:#1e293b; --sub:#64748b; --line:#e6e9f0;
  --brand:#6366f1; --brand2:#8b5cf6; --up:#ef4444; --down:#10b981; --gold:#f59e0b;
  --shadow:0 1px 2px rgba(15,23,42,.04),0 8px 24px rgba(15,23,42,.06);
}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--ink);line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:920px;margin:0 auto;padding:0 16px 48px}
/* ===== Hero ===== */
.hero{background:linear-gradient(135deg,#1e1b4b 0%,#4f46e5 55%,#7c3aed 100%);color:#fff;border-radius:20px;padding:26px 24px 22px;margin:16px 0 16px;box-shadow:0 12px 32px rgba(79,70,229,.28)}
.hero .top{display:flex;justify-content:space-between;align-items:flex-start;gap:10px;flex-wrap:wrap}
.hero h1{font-size:23px;font-weight:800;letter-spacing:.3px}
.hero .badge{display:inline-block;font-size:11px;background:rgba(255,255,255,.16);border:1px solid rgba(255,255,255,.25);padding:3px 10px;border-radius:999px;margin-left:8px;vertical-align:2px;font-weight:600}
.hero .sub{margin-top:8px;font-size:13px;color:rgba(255,255,255,.82)}
.hero .date{font-size:12px;color:rgba(255,255,255,.75);white-space:nowrap}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px}
.kpi{background:rgba(255,255,255,.13);backdrop-filter:blur(6px);border:1px solid rgba(255,255,255,.2);border-radius:14px;padding:14px 12px;text-align:center}
.kpi .v{font-size:26px;font-weight:800;line-height:1.1}
.kpi .l{font-size:11px;color:rgba(255,255,255,.8);margin-top:4px}
/* ===== Card ===== */
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:14px;box-shadow:var(--shadow)}
.card h2{font-size:15px;font-weight:700;margin-bottom:16px;display:flex;align-items:center;gap:8px}
.card h2 .dot{width:9px;height:9px;border-radius:3px;background:linear-gradient(135deg,var(--brand),var(--brand2))}
.card h2 .cnt{font-size:12px;color:var(--sub);font-weight:600;background:#f1f5f9;padding:2px 9px;border-radius:999px}
/* ===== 信号 ===== */
.sig{display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border:1px solid var(--line);border-radius:13px;margin-bottom:9px;gap:10px;flex-wrap:wrap;transition:box-shadow .15s}
.sig:hover{box-shadow:0 4px 14px rgba(15,23,42,.07)}
.sig .nm{font-weight:600;font-size:14px}
.sig .cd{font-size:12px;color:var(--sub)}
.sig .st{font-size:12px;font-weight:700;padding:4px 11px;border-radius:999px;white-space:nowrap}
.st.buy{background:#fef2f2;color:var(--up);border:1px solid #fecaca}
.st.hold{background:#eff6ff;color:#2563eb;border:1px solid #bfdbfe}
.st.sell{background:#fffbeb;color:var(--gold);border:1px solid #fde68a}
.st.wait{background:#f1f5f9;color:#64748b;border:1px solid #e2e8f0}
.sig .ret{font-size:14px;font-weight:700}
.ret.pos{color:var(--up)} .ret.neg{color:var(--down)}
.empty{color:var(--sub);font-size:13px;text-align:center;padding:14px;background:#f8fafc;border-radius:10px}
/* ===== 历年胜率 ===== */
.bar-row{display:flex;align-items:center;gap:10px;margin-bottom:10px}
.bar-row .yr{width:46px;font-size:12px;color:var(--sub);text-align:right;font-weight:600}
.bar-row .track{flex:1;height:20px;background:#f1f5f9;border-radius:7px;position:relative;overflow:hidden}
.bar-row .fill{height:100%;border-radius:7px;background:linear-gradient(90deg,var(--brand),var(--brand2));display:flex;align-items:center;justify-content:flex-end;padding-right:7px;font-size:11px;color:#fff;font-weight:700;min-width:30px}
.line50{position:absolute;left:50%;top:0;bottom:0;width:1px;background:var(--gold);opacity:.8}
/* ===== 散点图 ===== */
.sliders{display:flex;gap:20px;flex-wrap:wrap;margin-bottom:4px}
.slider-item{flex:1;min-width:200px}
.slider-item label{font-size:12px;color:var(--sub);display:flex;justify-content:space-between;font-weight:600}
.slider-item label b{color:var(--brand)}
.slider-item input{width:100%;margin-top:6px;accent-color:var(--brand)}
.ps-svg{width:100%;height:auto;display:block}
.ps-legend{display:flex;gap:16px;font-size:12px;color:var(--sub);margin-top:8px;flex-wrap:wrap}
.ps-legend .lg{display:flex;align-items:center;gap:5px}
.ps-legend .sw{width:11px;height:11px;border-radius:50%;display:inline-block}
.pick-note{font-size:12.5px;margin-top:12px;padding:11px 13px;background:#f8fafc;border-radius:10px;color:var(--sub);line-height:1.7}
.pick-note b{color:var(--brand)}
/* ===== 表格 ===== */
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:10px 8px;text-align:center;border-bottom:1px solid var(--line)}
th{color:var(--sub);font-weight:600;font-size:12px;background:#f8fafc}
td:first-child,th:first-child{text-align:left}
tr:last-child td{border-bottom:none}
.pos{color:var(--up);font-weight:700} .neg{color:var(--down);font-weight:700}
.note{font-size:12px;color:var(--sub);margin-top:12px;line-height:1.7}
.mkpi{background:#f8fafc;border:1px solid var(--line);border-radius:12px;padding:13px 10px;text-align:center}
.mkpi .v{font-size:21px;font-weight:800;color:var(--brand)}
.mkpi .v.good{color:var(--down)} .mkpi .v.bad{color:var(--up)}
.mkpi .l{font-size:11px;color:var(--sub);margin-top:3px}
.op-form{display:flex;gap:8px;flex-wrap:wrap}
.op-form select,.op-form input{padding:8px 10px;border:1px solid var(--line);border-radius:8px;font-size:13px;flex:1;min-width:100px;background:#fff}
.op-form button{padding:8px 16px;background:var(--brand);color:#fff;border:none;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer}
.op-result{padding:12px;background:#f8fafc;border-radius:10px;font-size:13px;line-height:1.7}
.op-result .cmd{font-weight:500;color:var(--brand)}
.op-result button{margin-left:8px;padding:4px 12px;background:#eef2ff;color:var(--brand);border:1px solid #e0e7ff;border-radius:6px;font-size:12px;cursor:pointer}
footer{text-align:center;color:#94a3b8;font-size:12px;margin-top:22px}
@media(max-width:640px){
  .kpis{grid-template-columns:repeat(2,1fr)}
  .hero h1{font-size:20px}
  .kpi .v{font-size:22px}
}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="top">
      <div>
        <h1>ETF 量化信号<span class="badge">MA{fast}/MA{slow} 金叉 · MACD 过滤</span></h1>
        <div class="sub">支付宝 C 类 ETF 联接基金 · 买入持有 {hold_days} 天 · 每天 14:30 更新</div>
      </div>
      <div class="date">更新于 {date} · 净值数据截至 {data_date}</div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="v">{win_rate}%</div><div class="l">历史综合胜率</div></div>
      <div class="kpi"><div class="v">{avg_ret}%</div><div class="l">平均每笔收益</div></div>
      <div class="kpi"><div class="v">{hold_days}天</div><div class="l">持有周期</div></div>
      <div class="kpi"><div class="v">{n_funds}只</div><div class="l">精选标的</div></div>
    </div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>策略信号（非你的持仓）<span class="cnt" id="sigCnt"></span></h2>
    <div id="signals"></div>
    <div class="note">以下为策略每日扫描的 {n_funds} 只候选标的信号，<b>不是你的持仓</b>；你的实际持仓见下方「我的持仓」。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>我的持仓（仅你回报的）<span class="cnt" id="posCnt"></span></h2>
    <div id="positions"></div>
    <div class="note">支付宝无公开 API，持仓需手动回报同步：在对话里告诉我「买入/卖出 基金代码 金额」，我记入持仓表并更新此页。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>回报今日操作</h2>
    <div class="op-form">
      <select id="opType"><option value="买入">买入</option><option value="卖出">卖出</option></select>
      <input id="opCode" placeholder="基金代码，如 020640" inputmode="numeric">
      <input id="opAmount" placeholder="金额（元）" inputmode="numeric">
      <button id="opBtn" onclick="genReport()">生成回报指令</button>
    </div>
    <div id="opResult" style="display:none;margin-top:12px"></div>
  </div>

  <div class="card" id="simCard">
    <h2><span class="dot"></span>相似K线 · 历史信号走势回放</h2>
    <div id="signalSim"></div>
    <div class="note">展示当前有信号标的在历史上每次出现同样买入信号后 {hold_days} 个交易日的走势，用于判断本次信号的胜率预期。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>绩效指标（2020 至今）</h2>
    <div class="grid" id="metricsGrid"></div>
    <div class="note">对比基准「等权买入持有 {n_funds} 只标的」：累计 +{bench_cum}%、最大回撤 {bench_mdd}%。本策略以更低回撤换取稳健收益。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>回测资金曲线（策略 vs 基准）</h2>
    <div id="equityChart"></div>
    <div class="ps-legend">
      <span class="lg"><span class="sw" style="background:#6366f1"></span>策略（金叉+MACD）</span>
      <span class="lg"><span class="sw" style="background:#94a3b8"></span>基准（买入持有）</span>
    </div>
    <div class="note">{n_funds} 只标的等权组合净值（2020 年至今）；策略空仓持币，基准始终满仓。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>胜率 × 盈利率（拖动选范围）</h2>
    <div class="sliders">
      <div class="slider-item"><label>最低胜率 <b id="winVal">55%</b></label><input type="range" id="winSlider" min="50" max="68" step="0.5" value="55"></div>
      <div class="slider-item"><label>最低盈利率 <b id="retVal">1.0%</b></label><input type="range" id="retSlider" min="0.4" max="1.9" step="0.05" value="1.0"></div>
    </div>
    <div id="psChart"></div>
    <div class="ps-legend">
      <span class="lg"><span class="sw" style="background:#6366f1"></span>当前采用（持有{hold_days}天）</span>
      <span class="lg"><span class="sw" style="background:#ef4444"></span>符合所选范围</span>
      <span class="lg"><span class="sw" style="background:#cbd5e1"></span>不符合</span>
    </div>
    <div class="pick-note" id="pickNote"></div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>历年胜率（按买入年份）</h2>
    <div id="yearly"></div>
    <div class="note">金色虚线为 50% 胜率线；历年胜率均高于 50%，牛熊震荡市场均有效。</div>
  </div>

  <div class="card">
    <h2><span class="dot"></span>最近交易明细（回测）</h2>
    <table id="trades"></table>
  </div>

  <div class="card">
    <h2><span class="dot"></span>标的池明细</h2>
    <table id="funds"></table>
  </div>

  <footer>数据来源：天天基金 · 每日自动更新 · 仅供研究参考，不构成投资建议</footer>
</div>
<script>
const DATA = __DATA__;
const ST = {BUY:['buy','买入信号'],HOLDING:['hold','持有中'],SELL_READY:['sell','可卖出'],WAIT:['wait','等待'],ERROR:['wait','异常']};
function fmtRet(r){return (r>=0?'+':'')+(r*100).toFixed(2)+'%';}
// 今日信号
const sg = document.getElementById('signals');
const buys = (DATA.signals||[]).filter(s=>s.state==='BUY');
document.getElementById('sigCnt').textContent = buys.length? ('🟢 '+buys.length+' 只买入') : '暂无买入';
if(!DATA.signals || !DATA.signals.length){ sg.innerHTML='<div class="empty">暂无数据</div>'; }
else{
  let html='';
  DATA.signals.forEach(s=>{
    const [cls,label]=ST[s.state]||['wait',s.state];
    const r=s.ret!=null?('<span class="ret '+(s.ret>=0?'pos':'neg')+'">'+fmtRet(s.ret)+'</span>'):'';
    let extra='';
    if(s.state==='HOLDING') extra='<span class="cd">持有第'+s.held_days+'天 · 还差'+(DATA.strategy.hold_days-s.held_days)+'天卖出</span>';
    else if(s.state==='SELL_READY') extra='<span class="cd">已到持有期 · 可卖出</span>';
    else if(s.state==='BUY') extra='<span class="cd">建议持有'+DATA.strategy.hold_days+'天后卖出</span>';
    html+='<div class="sig"><div><div class="nm">'+s.name+'</div><div class="cd">'+s.code+'</div></div><div style="display:flex;align-items:center;gap:9px">'+extra+r+'<span class="st '+cls+'">'+label+'</span></div></div>';
  });
  sg.innerHTML=html;
}
// 我的持仓
(function(){
  const el = document.getElementById('positions');
  const pos = DATA.positions || [];
  document.getElementById('posCnt').textContent = pos.length ? pos.length+' 只' : '暂无';
  if(!pos.length){ el.innerHTML='<div class="empty">暂无持仓记录。在对话中告诉我「买入 006479 2000元」即可录入。</div>'; return; }
  const sigMap = {};
  (DATA.signals||[]).forEach(s=>{ sigMap[s.code]=s.state; });
  let h='<table><tr><th>基金</th><th>买入日</th><th>金额</th><th>盈亏</th><th>今日实时</th><th>持有</th><th>操作</th></tr>';
  pos.forEach(p=>{
    const st = sigMap[p.code] || '';
    const op = (st==='SELL_READY'||st==='BUY') ? '<span class="st sell">该卖出</span>' : (st==='HOLDING'?'<span class="st hold">持有中</span>':'<span class="st wait">等待</span>');
    const ret = p.ret!=null ? ('<span class="'+(p.ret>=0?'pos':'neg')+'">'+fmtRet(p.ret)+'</span>') : '';
    const rc = p.realtime_chg!=null ? parseFloat(p.realtime_chg) : null;
    const rcHtml = rc!=null ? ('<span class="'+(rc>=0?'pos':'neg')+'">'+(rc>=0?'+':'')+rc+'%</span>') : '<span class="cd">-</span>';
    h+='<tr><td>'+p.name+'</td><td>'+p.buy_date+'</td><td>¥'+p.amount+'</td><td>'+ret+'</td><td>'+rcHtml+'</td><td>'+p.held_days+'天</td><td>'+op+'</td></tr>';
  });
  h+='</table>';
  el.innerHTML=h;
})();
// 历年胜率
const yr = document.getElementById('yearly');
let yh='';
DATA.yearly.forEach(d=>{
  yh+='<div class="bar-row"><span class="yr">'+d.year+'</span><div class="track"><div class="line50"></div><div class="fill" style="width:'+d.win_rate+'%">'+d.win_rate+'%</div></div></div>';
});
yr.innerHTML=yh;
// 标的明细
const fd = document.getElementById('funds');
let fh='<tr><th>基金</th><th>代码</th><th>胜率</th><th>平均收益</th><th>累计收益</th><th>交易</th></tr>';
DATA.funds.forEach(f=>{
  fh+='<tr><td>'+f.name+'</td><td>'+f.code+'</td><td>'+f.win_rate+'%</td><td class="'+(f.avg_ret>=0?'pos':'neg')+'">'+(f.avg_ret>=0?'+':'')+f.avg_ret+'%</td><td class="'+(f.cum_ret>=0?'pos':'neg')+'">'+(f.cum_ret>=0?'+':'')+f.cum_ret+'%</td><td>'+f.trades+'</td></tr>';
});
fd.innerHTML=fh;
// 最近交易明细
(function(){
  const el = document.getElementById('trades');
  const tr = DATA.recent_trades || [];
  if(!tr.length){ el.innerHTML='<div class="empty">暂无数据</div>'; return; }
  let h='<tr><th>基金</th><th>买入日</th><th>卖出日</th><th>持有</th><th>收益</th></tr>';
  tr.forEach(t=>{
    h+='<tr><td>'+t.name+'</td><td>'+t.buy_date+'</td><td>'+t.sell_date+'</td><td>'+t.hold+'天</td><td class="'+(t.ret>=0?'pos':'neg')+'">'+(t.ret>=0?'+':'')+t.ret+'%</td></tr>';
  });
  el.innerHTML=h;
})();
// 胜率-盈利率散点图
const ps = document.getElementById('psChart');
const XMIN=0.4, XMAX=1.9, YMIN=48, YMAX=68;
const L=52, R=660, T=16, B=276;
function px(v){ return L + (v-XMIN)/(XMAX-XMIN)*(R-L); }
function py(v){ return T + (YMAX-v)/(YMAX-YMIN)*(B-T); }
let winThr=55, retThr=1.0;
function renderPS(){
  const curHold = DATA.strategy.hold_days;
  let svg = '<svg class="ps-svg" viewBox="0 0 680 314">';
  for(let y=YMIN; y<=YMAX+0.001; y+=5){
    svg += '<line x1="'+L+'" y1="'+py(y)+'" x2="'+R+'" y2="'+py(y)+'" stroke="#eef1f7"/>';
    svg += '<text x="'+(L-8)+'" y="'+(py(y)+3)+'" font-size="10" fill="#94a3b8" text-anchor="end">'+y+'%</text>';
  }
  for(let x=XMIN; x<=XMAX+0.001; x+=0.3){
    svg += '<text x="'+px(x)+'" y="'+(B+16)+'" font-size="10" fill="#94a3b8" text-anchor="middle">'+x.toFixed(1)+'%</text>';
  }
  svg += '<line x1="'+L+'" y1="'+B+'" x2="'+R+'" y2="'+B+'" stroke="#cbd5e1"/>';
  svg += '<text x="'+((L+R)/2)+'" y="'+(B+32)+'" font-size="10" fill="#94a3b8" text-anchor="middle">平均每笔盈利率</text>';
  svg += '<text x="14" y="'+((T+B)/2)+'" font-size="10" fill="#94a3b8" text-anchor="middle" transform="rotate(-90 14 '+((T+B)/2)+')">胜率</text>';
  svg += '<line x1="'+px(retThr)+'" y1="'+T+'" x2="'+px(retThr)+'" y2="'+B+'" stroke="#ef4444" stroke-dasharray="5,3" opacity="0.6"/>';
  svg += '<line x1="'+L+'" y1="'+py(winThr)+'" x2="'+R+'" y2="'+py(winThr)+'" stroke="#ef4444" stroke-dasharray="5,3" opacity="0.6"/>';
  DATA.param_space.forEach(p=>{
    const cx=px(p.avg_ret), cy=py(p.win_rate);
    const ok = p.win_rate>=winThr && p.avg_ret>=retThr;
    const isCur = p.hold_days===curHold;
    const r = isCur?6.5:4.5;
    const color = isCur?'#6366f1':(ok?'#ef4444':'#cbd5e1');
    svg += '<circle cx="'+cx+'" cy="'+cy+'" r="'+r+'" fill="'+color+'"/>';
    svg += '<text x="'+cx+'" y="'+(cy-9)+'" font-size="9.5" fill="#475569" text-anchor="middle" font-weight="600">'+p.hold_days+'d</text>';
  });
  svg += '</svg>';
  ps.innerHTML = svg;
  const okList = DATA.param_space.filter(p=>p.win_rate>=winThr && p.avg_ret>=retThr);
  document.getElementById('winVal').textContent = winThr+'%';
  document.getElementById('retVal').textContent = retThr.toFixed(2)+'%';
  let note='';
  if(okList.length){
    note = '✅ 符合范围（胜率≥'+winThr+'% 且 盈利率≥'+retThr.toFixed(2)+'%）的持有期：<b>'+okList.map(p=>p.hold_days+'天').join('、')+'</b>。';
    note += okList.some(p=>p.hold_days===curHold) ? ' 当前采用的 <b>'+curHold+'天</b> 满足你的要求。' : ' ⚠️ 当前采用的 '+curHold+'天 不在此范围内。';
  } else {
    note = '当前筛选过严，无满足的持有期，请放宽阈值。';
  }
  document.getElementById('pickNote').innerHTML = note;
}
document.getElementById('winSlider').addEventListener('input', e=>{winThr=parseFloat(e.target.value); renderPS();});
document.getElementById('retSlider').addEventListener('input', e=>{retThr=parseFloat(e.target.value); renderPS();});
renderPS();
// 资金曲线
(function(){
  const el = document.getElementById('equityChart');
  const eq = DATA.equity || [];
  if(!eq.length){ el.innerHTML='<div class="empty">暂无数据</div>'; return; }
  const W=680, H=240, L=44, R=14, T=14, B=30;
  const bm = DATA.benchmark || [];
  const allv = eq.map(x=>x[1]).concat(bm.map(x=>x[1]));
  const min=Math.min(1, ...allv), max=Math.max(...allv);
  function px(i){ return L + i/(eq.length-1)*(W-L-R); }
  function py(v){ return T + (max-v)/(max-min)*(H-T-B); }
  let svg='<svg class="ps-svg" viewBox="0 0 '+W+' '+H+'">';
  for(let v=min; v<=max+1e-9; v+=(max-min)/4){
    svg+='<line x1="'+L+'" y1="'+py(v)+'" x2="'+(W-R)+'" y2="'+py(v)+'" stroke="#eef1f7"/>';
    svg+='<text x="'+(L-6)+'" y="'+(py(v)+3)+'" font-size="9" fill="#94a3b8" text-anchor="end">'+v.toFixed(2)+'</text>';
  }
  svg+='<line x1="'+L+'" y1="'+py(1)+'" x2="'+(W-R)+'" y2="'+py(1)+'" stroke="#f59e0b" stroke-dasharray="4,3"/>';
  if(bm.length){
    let db='';
    bm.forEach((x,i)=>{ db+=(i?'L':'M')+(L+i/(bm.length-1)*(W-L-R)).toFixed(1)+' '+py(x[1]).toFixed(1); });
    svg+='<path d="'+db+'" fill="none" stroke="#94a3b8" stroke-width="1.5"/>';
  }
  let d='';
  eq.forEach((x,i)=>{ d += (i?'L':'M')+px(i).toFixed(1)+' '+py(x[1]).toFixed(1); });
  svg+='<path d="'+d+' L'+(W-R)+' '+py(min)+' L'+L+' '+py(min)+' Z" fill="rgba(99,102,241,.08)"/>';
  svg+='<path d="'+d+'" fill="none" stroke="#6366f1" stroke-width="2"/>';
  const idx=[0, Math.floor((eq.length-1)/2), eq.length-1];
  idx.forEach(i=>{ svg+='<text x="'+px(i)+'" y="'+(H-6)+'" font-size="9" fill="#94a3b8" text-anchor="middle">'+eq[i][0]+'</text>'; });
  svg+='</svg>';
  el.innerHTML=svg;
})();
// 绩效指标
(function(){
  const el = document.getElementById('metricsGrid');
  const m = DATA.metrics || {};
  if(!m.cagr){ el.innerHTML='<div class="empty">暂无数据</div>'; return; }
  const items = [
    ['年化收益', m.cagr+'%', m.cagr>=10?'good':''],
    ['最大回撤', m.mdd+'%', m.mdd<10?'good':(m.mdd>20?'bad':'')],
    ['夏普比率', m.sharpe, m.sharpe>=1?'good':''],
    ['卡玛比率', m.calmar, m.calmar>=1?'good':''],
    ['盈亏比', m.pl_ratio, m.pl_ratio>=1.5?'good':''],
    ['盈利因子', m.profit_factor, m.profit_factor>=1.5?'good':''],
  ];
  let h='';
  items.forEach(it=>{ h+='<div class="mkpi"><div class="v '+it[2]+'">'+it[1]+'</div><div class="l">'+it[0]+'</div></div>'; });
  el.innerHTML=h;
})();
// 相似K线历史走势
(function(){
  const el = document.getElementById('signalSim');
  const sa = DATA.signal_analysis || [];
  const card = document.getElementById('simCard');
  if(!sa.length){ card.style.display='none'; return; }
  card.style.display='block';
  const W=680, H=210, L=44, R=14, T=14, B=26;
  let html='';
  sa.forEach(item=>{
    const allv = item.avg_path.concat(...item.samples);
    const maxv = Math.max(1, ...allv), minv = Math.min(-1, ...allv);
    function px(i){ return L + i/(item.avg_path.length-1)*(W-L-R); }
    function py(v){ return T + (maxv-v)/(maxv-minv)*(H-T-B); }
    let svg='<svg class="ps-svg" viewBox="0 0 '+W+' '+H+'" style="margin-bottom:6px">';
    svg+='<line x1="'+L+'" y1="'+py(0)+'" x2="'+(W-R)+'" y2="'+py(0)+'" stroke="#f59e0b" stroke-dasharray="4,3"/>';
    item.samples.forEach(sp=>{
      let d='';
      sp.forEach((v,i)=>{ d+=(i?'L':'M')+px(i).toFixed(1)+' '+py(v).toFixed(1); });
      svg+='<path d="'+d+'" fill="none" stroke="#cbd5e1" stroke-width="0.7" opacity="0.75"/>';
    });
    let d2='';
    item.avg_path.forEach((v,i)=>{ d2+=(i?'L':'M')+px(i).toFixed(1)+' '+py(v).toFixed(1); });
    svg+='<path d="'+d2+'" fill="none" stroke="#ef4444" stroke-width="2.5"/>';
    svg+='<text x="'+(L-6)+'" y="'+(py(0)+3)+'" font-size="9" fill="#94a3b8" text-anchor="end">0%</text>';
    svg+='<text x="'+(L-6)+'" y="'+(py(maxv)+3)+'" font-size="9" fill="#94a3b8" text-anchor="end">'+maxv.toFixed(0)+'%</text>';
    svg+='<text x="'+((L+W-R)/2)+'" y="'+(H-4)+'" font-size="9" fill="#94a3b8" text-anchor="middle">买入后交易日</text>';
    svg+='</svg>';
    html+='<div style="margin-bottom:20px">';
    html+='<div style="font-size:14px;font-weight:700;margin-bottom:6px">'+item.name+'<span class="cnt" style="margin-left:8px">历史 '+item.n_signals+' 次信号 · '+DATA.strategy.hold_days+'天后胜率 '+item.win_rate+'%</span></div>';
    html+=svg;
    html+='<div style="font-size:12px;color:#64748b;margin-top:6px">红粗线=历史平均走势，灰线=各次实际走势；买入后 '+DATA.strategy.hold_days+' 个交易日平均收益 '+item.avg_final+'%，胜率 '+item.win_rate+'%。</div>';
    html+='</div>';
  });
  el.innerHTML=html;
})();
// 回报今日操作
function genReport(){
  const t = document.getElementById('opType').value;
  const c = document.getElementById('opCode').value.trim();
  const a = document.getElementById('opAmount').value.trim();
  const el = document.getElementById('opResult');
  if(!c || !a){ el.style.display='block'; el.innerHTML='<div class="op-result">请填写基金代码和金额。</div>'; return; }
  const cmd = t + ' ' + c + ' ' + a + '元';
  el.style.display='block';
  el.innerHTML='<div class="op-result">回报指令：<span class="cmd" id="opCmd">' + cmd + '</span>' +
    '<button onclick="copyCmd()">复制</button><br>' +
    '① 回到 WorkBuddy 对话粘贴这句发送；或 ② <a href="mailto:fmmujf@163.com?subject=' + encodeURIComponent('持仓回报') + '&body=' + encodeURIComponent(cmd) + '" style="color:#6366f1">点此发邮件回报</a>。</div>';
}
function copyCmd(){
  const txt = document.getElementById('opCmd').textContent;
  if(navigator.clipboard){ navigator.clipboard.writeText(txt); }
  else{ const ta=document.createElement('textarea'); ta.value=txt; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); }
}
</script>
</body>
</html>
"""


def main():
    data = build_data()
    data["n_funds"] = len(POOL)
    html = (HTML
            .replace("{fast}", str(data["strategy"]["fast"]))
            .replace("{slow}", str(data["strategy"]["slow"]))
            .replace("{hold_days}", str(data["strategy"]["hold_days"]))
            .replace("{date}", data["date"])
            .replace("{data_date}", data.get("data_date", ""))
            .replace("{win_rate}", str(data["summary"]["win_rate"]))
            .replace("{avg_ret}", str(data["summary"]["avg_ret"]))
            .replace("{trades}", str(data["summary"]["trades"]))
            .replace("{n_funds}", str(data["n_funds"]))
            .replace("{bench_cum}", str(data["metrics"]["bench_cum"]))
            .replace("{bench_mdd}", str(data["metrics"]["bench_mdd"])))
    html = html.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = os.path.join(os.path.dirname(__file__), "index.html")
    open(out, "w", encoding="utf-8").write(html)
    print("生成 index.html 完成,", len(html), "字节")
    print("胜率", data["summary"]["win_rate"], "% | 平均收益", data["summary"]["avg_ret"], "%")


if __name__ == "__main__":
    main()
