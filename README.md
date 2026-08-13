# ETF 量化交易自动化系统

无人值守的 ETF 量化策略自动化运行系统：每天定时完成「数据获取 → 信号计算 → 回测 → 结果记录 → 邮件通知」全流程。纯 Python 标准库实现，无第三方依赖，可迁移、易部署。

## 在线页面

**https://jivonkiang.github.io/etf-quant-auto/** （电脑 / 手机均可访问，每日自动更新）

## 特性

- **相对路径**：所有运行数据（净值缓存 / 信号 / 交易 / 日志）都落在 `data/` 下，路径以项目根目录为锚点，不依赖机器绝对路径。
- **无人值守**：GitHub Actions 云上定时执行（本地电脑关机也能跑），另有 WorkBuddy 自动化做本地触发 + 邮件通知兜底。
- **清晰结构**：`core/` 各模块职责单一；`config.json` 集中配置。
- **稳定可靠**：网络请求自动重试（指数退避）、单只标的异常不中断、日志全程落盘可回溯。

## 项目结构

```
etf-quant-auto/
├── config.json              # 集中配置（运行时间/数据路径/策略参数/回测实盘开关/重试/邮件/持仓提醒）
├── run_daily.py             # 每日主入口（编排全流程）
├── build_site.py            # 生成 GitHub Pages 前端 index.html
├── index.html               # 前端页面（build_site 自动生成）
├── core/                    # 核心模块
│   ├── config.py            #   配置加载 + 相对路径解析
│   ├── logger.py            #   日志（控制台 + data/logs/）
│   ├── utils.py             #   自动重试 / 目录确保
│   ├── data_fetcher.py      #   数据获取（天天基金净值 + 腾讯实时，带缓存）
│   ├── indicators.py        #   技术指标（MA/EMA/MACD）
│   ├── strategy.py          #   策略（金叉+MACD 买入，持有/止盈卖出）
│   ├── backtest.py          #   回测引擎（资金曲线 + 绩效指标）
│   ├── executor.py          #   实盘信号检测与执行
│   ├── position_alert.py    #   持仓买卖提醒（止盈/止损/破位/加仓）
│   ├── reporter.py          #   结果记录（信号/交易/报告落盘）
│   └── notifier.py          #   邮件通知（SMTP）
├── data/                    # 运行数据（相对路径，自动创建）
│   ├── positions.json       #   用户实际持仓（手动回报录入）
│   ├── nav_cache/           #   净值缓存（不入库）
│   ├── signals/             #   每日信号 + 回测结果
│   ├── trades/              #   交易明细
│   └── logs/                #   运行日志
└── .github/workflows/daily.yml  # 云上定时执行 + gh-pages 部署
```

## 配置说明（config.json）

| 配置项 | 说明 |
|--------|------|
| `schedule.run_time` | 每日运行时间（北京时间，参考值；实际调度由自动化/cron 控制） |
| `paths.*` | 数据保存路径（相对项目根目录） |
| `strategy.*` | 策略参数：均线周期、持有天数、止盈、MACD 过滤、标的池、场外→场内映射 |
| `mode.backtest_enabled` | 每日是否跑回测 |
| `mode.live_enabled` | 每日是否跑实盘信号（记录 + 通知） |
| `notify.email_enabled` | 是否发邮件（SMTP 账号从环境变量读） |
| `retry.*` | 网络请求重试次数与退避间隔 |

## 本地运行

```bash
python run_daily.py                # 全流程
python run_daily.py --live-only    # 仅实盘信号
python run_daily.py --backtest-only
python run_daily.py --no-mail      # 不发邮件
```

## 邮件配置

SMTP 账号从环境变量读取（不入库明文）：`MAIL_SERVER` / `MAIL_PORT` / `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_TO`。

## 免责声明

本系统输出的信号与回测结果为模型驱动，仅供研究参考，不构成投资建议或个股推荐。投资有风险，决策需谨慎。
