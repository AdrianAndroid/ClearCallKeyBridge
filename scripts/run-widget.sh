#!/usr/bin/env bash
# 一键启动常驻置顶工具条（macOS/Linux 通用，无第三方依赖）
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 -m clearcall200 --widget "${1:-bar}"
