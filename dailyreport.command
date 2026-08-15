#!/bin/bash
set -e
cd "$(dirname "$0")"

PY=".venv/bin/python"

# 首次运行：创建虚拟环境
if [ ! -f "$PY" ]; then
    echo "[dailyreport] 首次运行，正在创建虚拟环境..."
    python3 -m venv .venv
fi

# 首次运行或依赖更新：安装依赖
if [ ! -f ".venv/.deps_installed" ] || [ requirements.txt -nt .venv/.deps_installed ]; then
    echo "[dailyreport] 正在安装依赖..."
    "$PY" -m pip install -r requirements.txt
    touch .venv/.deps_installed
fi

# 首次运行：提示配置 .env
if [ ! -f ".env" ]; then
    echo "[dailyreport] 未找到 .env，请复制 .env.example 为 .env 并填写 API Key。"
fi

exec "$PY" main.py
