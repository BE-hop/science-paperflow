#!/bin/zsh
set -e

PROJECT_DIR="${0:A:h}"
PYTHON_BIN="/opt/anaconda3/bin/python"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

cd "$PROJECT_DIR"

if ! "$PYTHON_BIN" -c 'import fastapi, jinja2, multipart, uvicorn, yaml' 2>/dev/null; then
  osascript -e 'display alert "Paperflow 尚未安装网页依赖" message "请让 Agent 在 science 项目中完成一次安装和检查。" as critical'
  exit 1
fi

exec "$PYTHON_BIN" -m paperflow web
