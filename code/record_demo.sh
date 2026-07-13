#!/usr/bin/env bash
# Agent 技术笔试题 · 录屏演示脚本
# 用法：./record_demo.sh
# 录制建议：先打开 QuickTime Player → 文件 → 新建屏幕录制 → 选择窗口
# 录制时执行本脚本即可

set -e
cd "$(dirname "$0")"

# ====== 颜色 ======
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

# ====== API Key 配置 ======
export ANTHROPIC_BASE_URL="${ANTHROPIC_BASE_URL:-https://api.minimaxi.com/anthropic}"
export AGENT_MODEL="${AGENT_MODEL:-MiniMax-M3}"
if [[ -z "$ANTHROPIC_API_KEY" ]]; then
    echo -e "${RED}✗ 错误：未设置 ANTHROPIC_API_KEY${NC}"
    echo "请先执行：export ANTHROPIC_API_KEY=sk-..."
    exit 1
fi

# ====== 辅助函数 ======
section() {
    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║${NC} ${YELLOW}$1${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

pause() {
    echo ""
    echo -e "${GREEN}>>> 按 Enter 继续...${NC}"
    read -r
}

slow_print() {
    # 让输出慢一点，录屏时更容易看清
    while IFS= read -r line; do
        echo "$line"
        sleep 0.05
    done
}

# ============================================================
# 1. 项目结构
# ============================================================
section "1/6 项目结构"
echo -e "${BLUE}代码目录文件清单：${NC}"
find . -type f \( -name "*.py" -o -name "*.md" -o -name "*.txt" -o -name "*.sh" \) \
    -not -path "*/\.*" -not -path "*/__pycache__/*" | sort
echo ""
echo -e "${BLUE}核心代码行数统计：${NC}"
wc -l agent/*.py tools/*.py main.py config.py 2>/dev/null | tail -10
pause

# ============================================================
# 2. 全部测试（73 个）
# ============================================================
section "2/6 运行全部测试（73 个）"
echo -e "${BLUE}执行：python3 -m pytest tests/ -v${NC}"
echo ""
python3 -m pytest tests/ -v --tb=short
pause

# ============================================================
# 3. CLI 完整演示：三个工具 + 多轮记忆
# ============================================================
section "3/6 CLI 演示：三个工具 + 跨轮记忆"
echo -e "${BLUE}启动 CLI，使用 --trace 模式（显示状态机切换）${NC}"
echo ""
printf '请用 calculator 工具计算 25*4+10，不要手算
用 todo 工具添加：买菜
用 todo 工具再添加：写报告
请用 todo 工具列出我的待办
请用 search 工具查东京天气
/quit
' | python3 main.py --trace
pause

# ============================================================
# 4. Robustness 演示：之前会嘴炮的输入
# ============================================================
section "4/6 Robustness：自答检测 + retry 强制调工具"
echo -e "${BLUE}场景：M3 模型有时会说'我来帮你算'但实际不调工具${NC}"
echo -e "${BLUE}runtime 现在会自动检测自答并强制 retry${NC}"
echo ""
python3 -c "
import sys
sys.path.insert(0, '.')
import agent.tools, tools.calculator, tools.search, tools.todo
from agent.runtime import AgentRuntime
from agent.context import Context
from agent.trace import Trace

tests = [
    ('100 + 200 * 3 等于多少？', '数学自答检测'),
    ('东京天气怎么样？', '外部信息检测'),
    ('帮我记住买菜这件事', '待办检测'),
]
for q, desc in tests:
    print(f'\n--- {desc}: \"{q}\" ---')
    rt = AgentRuntime('demo', Context(), Trace(enabled=False))
    r = rt.run_turn(q)
    tools_used = [(tc['name'], tc['input']) for tc in r.tool_calls]
    print(f'rounds={r.rounds}, 工具调用={tools_used}')
    print(f'答案: {r.final_text[:120]}')
"
pause

# ============================================================
# 5. 多 Session 隔离
# ============================================================
section "5/6 Session 隔离：多窗口完全独立"
echo -e "${BLUE}先清空旧 session 文件${NC}"
rm -rf ~/.agent_sessions/session_*.json 2>/dev/null
echo ""
echo -e "${BLUE}列出当前所有 session：${NC}"
python3 main.py --list
echo ""
echo -e "${BLUE}窗口 A：让 todo 添加 2 件事${NC}"
printf '用 todo 工具添加：A窗口-任务1\n用 todo 工具添加：A窗口-任务2\n/quit\n' | python3 main.py --trace 2>&1 | grep -E '^\[assistant\]|trace.*rounds|Session saved'
echo ""
echo -e "${BLUE}窗口 B：新 session，查 todo 应该是空的${NC}"
printf '现在我有什么待办？\n/quit\n' | python3 main.py --trace 2>&1 | grep -E '^\[assistant\]|trace.*rounds|Session saved'
echo ""
echo -e "${BLUE}最终 session 列表（两个独立 session）：${NC}"
python3 main.py --list
pause

# ============================================================
# 6. 启动 CLI 主界面（交互模式，停留在这里）
# ============================================================
section "6/6 启动 Agent CLI 主界面"
echo -e "${BLUE}现在启动 main.py，进入交互模式${NC}"
echo -e "${YELLOW}（录屏会在此处停留，让面试官看到主程序界面）${NC}"
echo ""
echo -e "${GREEN}提示：面试官可以在这里看到:${NC}"
echo "  • Banner（项目标题 + Model + Session ID）"
echo "  • 内置命令列表（/new, /list, /switch 等）"
echo "  • 提示符等待用户输入"
echo ""
echo -e "${CYAN}按 Enter 启动 CLI...${NC}"
read -r
clear

# 启动 main.py（interactive 模式）
python3 main.py