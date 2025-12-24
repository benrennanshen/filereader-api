#!/usr/bin/env bash
# filereader 服务管理脚本（类比 start.bat）
# 支持：启动 / 启动开发模式（热重载）/ 停止

set -euo pipefail

APP_ENTRY="main:app"
HOST="0.0.0.0"
PORT="8002"
PYTHON="${PYTHON:-python3}"
VENV_DIR=".venv"
VENV_BIN="$VENV_DIR/bin"
ACTIVATE="$VENV_BIN/activate"
PIP_BIN="$VENV_BIN/pip"
UVICORN_CMD="$PYTHON -m uvicorn $APP_ENTRY --host $HOST --port $PORT"
UVICORN_DEV_CMD="$UVICORN_CMD --reload"

info() { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }

ensure_venv() {
  if [[ -f "$ACTIVATE" ]]; then
    info "虚拟环境已存在：$VENV_DIR"
  else
    info "未找到虚拟环境，正在创建：$VENV_DIR"
    $PYTHON -m venv "$VENV_DIR" || { err "创建虚拟环境失败"; exit 1; }
  }
  # shellcheck disable=SC1090
  source "$ACTIVATE" || { err "激活虚拟环境失败"; exit 1; }
}

install_deps() {
  if [[ ! -x "$PIP_BIN" ]]; then
    warn "未找到 $PIP_BIN，使用全局 pip"
    PIP_BIN="pip"
  fi
  info "安装/更新依赖..."
  "$PIP_BIN" install -r requirements.txt --quiet --disable-pip-version-check || \
    warn "依赖安装失败，继续启动（请检查环境）"
}

kill_port() {
  local target_port="$1"
  local pids
  if command -v lsof >/dev/null 2>&1; then
    pids=$(lsof -ti tcp:"$target_port" || true)
  else
    # netstat 兼容
    pids=$(netstat -tunlp 2>/dev/null | awk -v port=":$target_port" '$4 ~ port {gsub("/.*","",$7); print $7}' || true)
  fi
  if [[ -n "$pids" ]]; then
    info "发现占用端口 $target_port 的进程：$pids，正在终止..."
    kill -9 $pids >/dev/null 2>&1 || warn "终止进程失败：$pids"
  else
    info "未检测到占用端口 $target_port 的进程"
  }
}

start_server() {
  local cmd="$1"
  info "启动服务：$cmd"
  echo "服务地址: http://localhost:$PORT"
  echo "按 Ctrl+C 停止"
  eval "$cmd"
}

usage() {
  cat <<'EOF'
用法: ./start.sh [命令]

命令：
  start       启动服务
  dev         启动开发模式（热重载）
  stop        停止占用端口的进程
  help        显示本帮助

示例：
  ./start.sh start
  ./start.sh dev
  ./start.sh stop
EOF
}

main() {
  local cmd="${1:-help}"
  case "$cmd" in
    start)
      info "检查并关闭旧进程..."
      kill_port "$PORT"
      info "准备环境..."
      ensure_venv
      install_deps
      start_server "$UVICORN_CMD"
      ;;
    dev)
      info "检查并关闭旧进程..."
      kill_port "$PORT"
      info "准备环境..."
      ensure_venv
      install_deps
      start_server "$UVICORN_DEV_CMD"
      ;;
    stop)
      kill_port "$PORT"
      ;;
    help|*)
      usage
      ;;
  esac
}

main "$@"

