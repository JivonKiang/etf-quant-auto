@echo off
rem ETF 模拟盘每日跑批（T 日收盘信号，T+1 开盘价撮合）
cd /d "E:\ai agent\etf-quant-auto"
python run_daily.py --paper-only --no-mail >> data\logs\schtasks.log 2>&1
