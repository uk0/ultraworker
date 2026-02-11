#!/usr/bin/env bash
# Ultraworker Setup Script
# Clone the repo, then run: bash setup.sh
set -e

echo "🚀 Ultraworker Setup"
echo "===================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3이 필요합니다. https://python.org 에서 설치하세요."
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Python $PYTHON_VERSION"

# Check/install uv
if ! command -v uv &>/dev/null; then
    echo "📦 uv 패키지 매니저 설치 중..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Add to PATH for current session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    if ! command -v uv &>/dev/null; then
        echo "❌ uv 설치 실패. 수동으로 설치해주세요:"
        echo "   curl -LsSf https://astral.sh/uv/install.sh | sh"
        exit 1
    fi
fi
echo "✅ uv $(uv --version 2>/dev/null || echo 'installed')"

# Check Node.js (optional but recommended)
if command -v node &>/dev/null; then
    echo "✅ Node.js $(node --version)"
else
    echo "⚠️  Node.js가 없습니다. 일부 MCP 기능에 필요합니다."
    echo "   https://nodejs.org/ 에서 설치를 권장합니다."
fi

# Check Claude Code
if command -v claude &>/dev/null; then
    echo "✅ Claude Code $(claude --version 2>/dev/null || echo 'installed')"
else
    echo "⚠️  Claude Code CLI가 없습니다."
    echo "   npm install -g @anthropic-ai/claude-code 로 설치하세요."
fi

echo ""
echo "📦 의존성 설치 중..."
uv sync

echo ""
echo "🎨 설치 위자드 시작 중..."
uv run ultrawork setup
