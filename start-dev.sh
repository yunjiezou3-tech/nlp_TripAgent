#!/bin/bash

# 开发环境启动脚本
# 确保前后端端口一致性

echo "🚀 启动开发环境..."

# 设置端口（可修改）
FRONTEND_PORT=8081
BACKEND_PORT=8000

# 检查端口是否可用
check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️  端口 $1 已被占用"
        return 1
    else
        echo "✅ 端口 $1 可用"
        return 0
    fi
}

echo "🔍 检查端口状态..."
check_port $FRONTEND_PORT
check_port $BACKEND_PORT

echo ""
echo "📦 启动后端服务..."
cd Vaiage
export PORT=$BACKEND_PORT
python3 main.py &
BACKEND_PID=$!

echo "💻 启动前端服务..."
cd ../nlp_tripagent_frontend
export VITE_PORT=$FRONTEND_PORT
npm run dev &
FRONTEND_PID=$!

echo ""
echo "🎯 开发环境启动完成！"
echo "前端: http://localhost:$FRONTEND_PORT"
echo "后端: http://127.0.0.1:$BACKEND_PORT"
echo ""
echo "按 Ctrl+C 停止所有服务"

# 等待中断信号
trap 'echo "🛑 停止服务..."; kill $BACKEND_PID $FRONTEND_PID; exit' INT
wait