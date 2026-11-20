#!/bin/bash
# 输入法悬浮球 · 启动器
# 双击即可运行；首次运行若缺少 PyQt6 会自动安装。
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 结束已在运行的旧实例（GUI 程序无端口，靠进程名匹配；避免重复叠加导致点击失效）
pkill -f "ime_float.py" 2>/dev/null
sleep 0.6

# 找一个能导入 PyQt6 的 python3；找不到就尝试安装
if ! python3 -c "import PyQt6" >/dev/null 2>&1; then
  echo "未检测到 PyQt6，正在安装（需要联网）..."
  python3 -m pip install --user --quiet PyQt6 2>&1 | tail -3
fi

exec python3 "$DIR/ime_float.py"
