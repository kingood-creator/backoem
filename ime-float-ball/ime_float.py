#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
输入法桌面悬浮球 (macOS / Windows)
==================================
一个常驻桌面的圆形悬浮图标，用于快速切换输入法。

功能：
  · 圆形悬浮图标，可拖拽到桌面任意位置（尺寸 40–160px 可调）
  · 整体透明度 100 级可调（右键「设置」或鼠标滚轮即时调整）
  · 图标背景可自定义（任选图片，自动裁剪为圆形；或纯色背景）
  · 左键点击（中上部）：在已启用的输入法之间循环切换
  · 左键点击（下边缘）：打开便签
  · 右键：弹出菜单（切换 / 图标大小 / 设置 / 便签 / 狗蛋书签 / 我的快捷(自定义) / 隐藏 / 退出）
  · 托盘图标：隐藏后可从托盘恢复，并可打开设置、便签、狗蛋书签、我的快捷（自定义项）
  · 我的快捷：可自定义任意右键项——「打开链接/程序」或「模拟快捷键」（如截图 Cmd+Shift+4），名字和快捷键自己填
  · 自动记忆位置、透明度、大小、背景、启用的输入法等

输入法切换的后端按平台自动选择（都是纯 ctypes，无第三方依赖）：
  · macOS   → Carbon / TIS       见 ime_mac.py
  · Windows → Win32 键盘布局     见 ime_win.py

依赖：PyQt6

运行：
  python3 ime_float.py        (macOS)
  python ime_float.py         (Windows)
"""

import os
import sys
import json
import re
import subprocess
import datetime

# ---------------------------------------------------------------------------
# 1) 输入法切换后端（纯 ctypes，无第三方依赖）
#    macOS → Carbon / TIS（ime_mac.py）
#    Windows → Win32 键盘布局（ime_win.py）
#    两者接口一致：list_sources() / current_id() / select_id(id)
# ---------------------------------------------------------------------------
if sys.platform.startswith("win"):
    from ime_win import WinIME as IMESwitch
else:
    from ime_mac import MacIME as IMESwitch

# 模拟键盘快捷键（纯 ctypes；macOS: CoreGraphics / Windows: SendInput）
from hotkey import send_key_combo, parse_combo



# ---------------------------------------------------------------------------
# 2) 配置读写
# ---------------------------------------------------------------------------
IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"


def open_target(target):
    """打开一个自定义目标（右键「我的快捷」项通用）：
    · 网址（http/https/ftp… 或 www. 开头）→ 浏览器打开；
    · macOS 的 .app → open -a 启动（程序自身会按需拉起本地服务）；
    · 本地文件 / 文件夹 → 用系统默认方式打开（macOS: open；Windows: startfile）；
    · 都不匹配 → 当作网址兜底。"""
    target = (target or "").strip()
    if not target:
        return
    target = os.path.expanduser(target)
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", target) or target.startswith("www."):
        u = target if "://" in target else "http://" + target
        QDesktopServices.openUrl(QUrl(u))
        return
    if IS_MAC and os.path.isdir(target) and target.lower().endswith(".app"):
        try:
            subprocess.run(["open", "-a", target], check=False)
        except Exception as e:
            print("打开程序失败：", e, file=sys.stderr)
        return
    if os.path.exists(target):
        if IS_MAC:
            subprocess.run(["open", target], check=False)
        else:
            try:
                os.startfile(target)
            except Exception as e:
                print("打开文件失败：", e, file=sys.stderr)
        return
    # 兜底：当网址处理
    QDesktopServices.openUrl(QUrl(target))


def _writable_dir(d):
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("1")
        os.remove(probe)
        return True
    except Exception:
        return False


def _data_dir():
    """配置与便签数据存哪儿。
    · 环境变量 IMEFLOAT_DATA 优先（想放哪放哪，最"绿色"）
    · Windows：程序所在目录下的 data/，不写注册表、不写 AppData，
      整个文件夹拷走就是完整的绿色版；若目录不可写（如放进 Program Files），
      自动退回到 %APPDATA%\\输入法悬浮球
    · macOS：沿用 ~/Library/Application Support/输入法悬浮球
    """
    env = os.environ.get("IMEFLOAT_DATA")
    if env:
        return os.path.abspath(env)
    if IS_WIN:
        base = (os.path.dirname(sys.executable) if getattr(sys, "frozen", False)
                else os.path.dirname(os.path.abspath(__file__)))
        portable = os.path.join(base, "data")
        if _writable_dir(portable):
            return portable
        return os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"),
                            "输入法悬浮球")
    return os.path.expanduser("~/Library/Application Support/输入法悬浮球")


CONFIG_DIR = _data_dir()
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "transparency": 100,   # 1~100，100 为完全不透明
    "bg_image": "",        # 自定义背景图片绝对路径；为空则用 bg_color
    "bg_color": "#3a7afe", # 纯色背景（无图片时生效）
    "position": None,      # [x, y]，None 表示使用默认右上角
    "icon_size": 84,       # 图标直径（逻辑像素），范围见 ICON_SIZE_MIN/MAX
    "enabled": [],         # 参与循环切换的输入法 ID；为空表示全部
    "login_start": False,  # 是否登录时启动
    "note_position": None,     # 便签窗口位置 [x, y]（透明度跟随悬浮球，见 transparency）
    "note_color": "#fff6c9",   # 便签纸面颜色
    "bookmark_app": "~/Desktop/狗蛋书签.app",  # 右键菜单「狗蛋书签」启动的本地程序（.app）
    "bookmark_url": "http://127.0.0.1:5184/", # 书签网页地址（程序起不来时的兜底）
    # 右键菜单「我的快捷」自定义项：每项 {"name", "kind", ...}
    #   kind="open"  → 打开 target（网址 / .app / 文件 / 文件夹）
    #   kind="keys"  → 发送 keys 组合键（如 "Cmd+Shift+4" / "Win+Shift+S"）
    # 默认带一个「截图」项，映射到当前系统的截图快捷键，开箱即用。
    "custom_items": [
        {"name": "截图", "kind": "keys",
         "keys": ("Win+Shift+S" if IS_WIN else "Cmd+Shift+4")},
    ],
}

# 图标直径的可调范围与基准值（基准 84 是原先写死的尺寸，所有绘制按它等比缩放）
ICON_SIZE_MIN = 40
ICON_SIZE_MAX = 160
ICON_SIZE_BASE = 84
ICON_SIZE_PRESETS = [("小", 56), ("标准", 84), ("大", 108), ("特大", 132)]


def clamp_icon_size(v, default=ICON_SIZE_BASE):
    """把任意输入收敛成合法的图标直径。"""
    try:
        v = int(round(float(v)))
    except (TypeError, ValueError):
        v = default
    return max(ICON_SIZE_MIN, min(ICON_SIZE_MAX, v))

# 非打字类的辅助输入源（表情符号面板 / 听写 / 长按等），默认不参与循环切换
AUX_BLACKLIST = {
    "com.apple.CharacterPaletteIM",
    "com.apple.inputmethod.ironwood",
    "com.apple.PressAndHold",
    "com.apple.KeyboardViewer",
    "com.apple.CharacterPicker",
}

# 辅助输入源的名字/ID 关键词（用于更宽松地过滤面板、听写等）
AUX_NAME_HINTS = ("palette", "dictation", "pressandhold", "keyboardviewer",
                 "characterpicker", "emoji", "symbols", "press and hold")


def is_aux(sid, name):
    if sid in AUX_BLACKLIST:
        return True
    hay = (sid + " " + (name or "")).lower()
    return any(h in hay for h in AUX_NAME_HINTS)


def get_display_sources(raw):
    """从原始输入源中过滤掉非打字类（面板/听写/长按等），并按名称去重：
    同一输入法的多个模式只保留一个，优先保留当前正在使用的模式。"""
    cur = IMESwitch.current_id()
    filtered = [s for s in raw if not is_aux(s["id"], s["name"])]
    groups = {}
    for s in filtered:
        groups.setdefault(s["name"] or s["id"], []).append(s)
    out = []
    for name, items in groups.items():
        ids = [i["id"] for i in items]
        if cur in ids:
            chosen = next(i for i in items if i["id"] == cur)
        else:
            # 优先保留「父级」输入法（ID 最短者），避免暴露模式子项
            chosen = min(items, key=lambda i: len(i["id"]))
        out.append(chosen)
    # 排序：macOS 上让 Apple 自带键盘布局优先，其余按名称；
    # Windows 上保持系统枚举顺序 —— 那正是 Win+Space 的循环顺序，重排会让用户对不上。
    if not IS_WIN:
        out.sort(key=lambda s: (0 if s["id"].startswith("com.apple.keylayout.") else 1, s["name"]))
    return out


def resolve_enabled(cfg_enabled, display_sources, all_sources):
    """把配置里的「参与循环切换」项解析成展示源列表。
    - 兼容两种存法：{'id','name'} 与旧的纯 ID 字符串；
    - 第三方输入法的 TIS ID 跨启动可能在「父级 / 模式」间变化（如
      com.tencent.inputmethod.wetype 与 ...wetype.pinyin），故按名称回退匹配；
    - 结果不足 2 个时等同全选，保证左键始终能循环（只选 1 个等于没有循环）。
    """
    by_id = {s["id"]: s for s in display_sources}
    by_name = {s["name"]: s for s in display_sources}

    def name_of(sid):
        for s in all_sources:
            if s["id"] == sid or s["id"].startswith(sid + ".") or sid.startswith(s["id"] + "."):
                return s["name"]
        return None

    out = []
    for item in (cfg_enabled or []):
        key = item.get("name") if isinstance(item, dict) else item
        if not key:
            continue
        src = by_name.get(key) or by_id.get(key)
        if src is None:  # 旧 ID 已失效 → 按名称回退
            nm = name_of(key)
            if nm:
                src = by_name.get(nm)
        if src is not None and not any(x["id"] == src["id"] for x in out):
            out.append(src)
    if len(out) < 2 and len(display_sources) >= 2:
        return list(display_sources)
    return out


def load_config():
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        for k, v in DEFAULT_CONFIG.items():
            cfg.setdefault(k, v)
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("保存配置失败：", e, file=sys.stderr)


# ---------------------------------------------------------------------------
# 2.1) 便签存储（自动保存 + 最近 3 版历史）
# ---------------------------------------------------------------------------
NOTE_PATH = os.path.join(CONFIG_DIR, "note.txt")
NOTE_HISTORY_PATH = os.path.join(CONFIG_DIR, "note_history.json")
NOTE_HISTORY_MAX = 3

# 便签预设纸面颜色（色板）
NOTE_PRESET_COLORS = [
    "#fff6c9",  # 暖黄
    "#ffd9e4",  # 蜜粉
    "#d7e8ff",  # 天蓝
    "#d6f5dd",  # 薄荷
    "#e7d9ff",  # 淡紫
    "#ffe0c2",  # 暖橙
    "#f0f0f0",  # 素灰
]


def load_note():
    try:
        with open(NOTE_PATH, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def save_note(text):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(NOTE_PATH, "w", encoding="utf-8") as f:
            f.write(text)
        return True
    except Exception as e:
        print("便签保存失败：", e, file=sys.stderr)
        return False


def load_note_history():
    try:
        with open(NOTE_HISTORY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return []


def save_note_history(hist):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(NOTE_HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump(hist, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("便签历史保存失败：", e, file=sys.stderr)


def short_label(name):
    """把输入法全名压缩成一个适合显示在圆圈里的短标签。"""
    if not name:
        return "?"
    if all(ord(ch) < 128 for ch in name):
        return name[:4]            # 纯 ASCII（如 ABC / Unicode）：最多 4 字符
    return name[0]                 # 含中文：取首字（微 / 搜 / 拼 ...）


# ---------------------------------------------------------------------------
# 3) GUI
# ---------------------------------------------------------------------------
from PyQt6.QtWidgets import (
    QApplication, QWidget, QMenu, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QSlider, QPushButton, QListWidget, QListWidgetItem, QColorDialog,
    QFileDialog, QSystemTrayIcon, QMessageBox, QCheckBox, QTextEdit, QFrame,
    QLineEdit, QComboBox, QKeySequenceEdit,
)
from PyQt6.QtCore import Qt, QTimer, QRect, QRectF, QPoint, QSize, QUrl, QKeyCombination
from PyQt6.QtGui import (
    QPainter, QPen, QColor, QPixmap, QIcon, QFont, QBrush, QAction, QRegion,
    QLinearGradient, QRadialGradient, QPainterPath, QCursor, QDesktopServices,
    QKeySequence,
)


def make_circle_pixmap(size, color="#3a7afe"):
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    base = QColor(color)
    grad = QLinearGradient(0, 0, 0, size)
    grad.setColorAt(0.0, base.lighter(114))
    grad.setColorAt(0.55, base)
    grad.setColorAt(1.0, base.darker(116))
    p.setBrush(QBrush(grad))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    # 发丝级深色描边，定义边缘
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor(0, 0, 0, 55), 1))
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return pix


# Qt.Key → 主键名（供 QKeySequence → "Cmd+Shift+4" 字符串转换）
_QTKEY_NAME = {
    Qt.Key.Key_Space: "Space", Qt.Key.Key_Tab: "Tab",
    Qt.Key.Key_Return: "Enter", Qt.Key.Key_Enter: "Enter",
    Qt.Key.Key_Escape: "Esc", Qt.Key.Key_Backspace: "Backspace",
    Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Home: "Home",
    Qt.Key.Key_End: "End", Qt.Key.Key_PageUp: "PageUp",
    Qt.Key.Key_PageDown: "PageDown", Qt.Key.Key_Insert: "Insert",
    Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
    Qt.Key.Key_Up: "Up", Qt.Key.Key_Down: "Down",
}
for _n in range(1, 13):
    _QTKEY_NAME[getattr(Qt.Key, f"Key_F{_n}")] = f"F{_n}"

# 反向表：按键名（小写）→ Qt.Key（供把存储字符串还原成 QKeySequence）
_KEYNAME_TO_QTKEY = {
    "space": Qt.Key.Key_Space, "tab": Qt.Key.Key_Tab,
    "enter": Qt.Key.Key_Return, "return": Qt.Key.Key_Return,
    "esc": Qt.Key.Key_Escape, "escape": Qt.Key.Key_Escape,
    "backspace": Qt.Key.Key_Backspace, "delete": Qt.Key.Key_Delete,
    "home": Qt.Key.Key_Home, "end": Qt.Key.Key_End,
    "pageup": Qt.Key.Key_PageUp, "pagedown": Qt.Key.Key_PageDown,
    "insert": Qt.Key.Key_Insert,
    "left": Qt.Key.Key_Left, "right": Qt.Key.Key_Right,
    "up": Qt.Key.Key_Up, "down": Qt.Key.Key_Down,
}
for _n in range(1, 13):
    _KEYNAME_TO_QTKEY[f"f{_n}"] = getattr(Qt.Key, f"Key_F{_n}")


def _key_name_to_qtkey(name):
    """把单个主键名（如 '4'、's'、'f5'、'space'）转成 Qt.Key；无法识别返回 None。"""
    if not name:
        return None
    n = name.lower()
    if len(n) == 1:
        o = ord(n.upper())
        if 0x20 <= o <= 0x7E:
            # 字母 / 数字：Qt.Key 的数值与 ASCII 一致（A=0x41，0=0x30 …）
            return Qt.Key(o)
    return _KEYNAME_TO_QTKEY.get(n)


def qkeycombo_to_str(kc):
    """把 QKeyCombination 转成 "Cmd+Shift+4" 形式（供 hotkey.send_key_combo 使用）。"""
    if kc is None:
        return ""
    m = kc.keyboardModifiers()
    parts = []
    if m & Qt.KeyboardModifier.MetaModifier:
        parts.append("Win" if not IS_MAC else "Cmd")
    if m & Qt.KeyboardModifier.ControlModifier:
        parts.append("Ctrl")
    if m & Qt.KeyboardModifier.AltModifier:
        parts.append("Option" if IS_MAC else "Alt")
    if m & Qt.KeyboardModifier.ShiftModifier:
        parts.append("Shift")
    k = kc.key()
    name = _QTKEY_NAME.get(k)
    if name is None and 32 <= int(k.value) <= 126:
        ch = chr(int(k.value))
        name = ch.upper() if ch.isalpha() else ch  # 字母大写更直观（如 S、F）
    if name is None:
        return ""
    parts.append(name)
    return "+".join(parts)


def qkeysequence_to_combo(seq):
    """把 QKeySequence（来自 QKeySequenceEdit）转成 "Cmd+Shift+4" 形式。"""
    if not seq or seq.count() == 0:
        return ""
    return qkeycombo_to_str(seq[0])


def combo_to_qkeysequence(combo):
    """把存储的 "Cmd+Shift+4" 形式还原成 QKeySequence（供编辑预填控件显示）。"""
    if not combo:
        return QKeySequence()
    parsed = parse_combo(combo)
    if not parsed:
        return QKeySequence()
    mods_words, key_name = parsed
    mods = Qt.KeyboardModifier.NoModifier
    for w in mods_words:
        if w in ("cmd", "command", "meta"):
            mods = mods | Qt.KeyboardModifier.MetaModifier
        elif w in ("win", "super", "windows"):
            mods = mods | Qt.KeyboardModifier.MetaModifier
        elif w in ("ctrl", "control"):
            mods = mods | Qt.KeyboardModifier.ControlModifier
        elif w in ("alt", "option"):
            mods = mods | Qt.KeyboardModifier.AltModifier
        elif w == "shift":
            mods = mods | Qt.KeyboardModifier.ShiftModifier
    k = _key_name_to_qtkey(key_name)
    if k is None:
        return QKeySequence()
    return QKeySequence(QKeyCombination(mods, k))


class CustomItemDialog(QDialog):
    """新增 / 编辑一个自定义右键菜单项：
    · 类型「打开链接/程序」：填网址 / .app / 文件 / 文件夹，点击即用系统方式打开；
    · 类型「模拟快捷键」：填组合键（如 Cmd+Shift+4 / Win+Shift+S），点击即向系统发送该按键。"""

    def __init__(self, parent=None, name="", target="", kind="open", keys=""):
        super().__init__(parent)
        self.setWindowTitle("添加 / 编辑快捷项")
        self.setMinimumWidth(480)
        v = QVBoxLayout(self)

        v.addWidget(QLabel("显示名称（右键菜单里看到的文字）："))
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("例如：狗蛋书签、截图、OpenAI…")
        v.addWidget(self.name_edit)

        v.addWidget(QLabel("类型："))
        self.type_combo = QComboBox()
        self.type_combo.addItem("打开链接 / 程序", "open")
        self.type_combo.addItem("模拟快捷键（向系统发送组合键）", "keys")
        self.type_combo.setCurrentIndex(0 if kind != "keys" else 1)
        self.type_combo.currentIndexChanged.connect(self._on_type)
        v.addWidget(self.type_combo)

        # —— 类型：打开链接/程序 ——
        self.open_widget = QWidget()
        ow = QVBoxLayout(self.open_widget)
        ow.setContentsMargins(0, 0, 0, 0)
        ow.addWidget(QLabel("链接或本地路径（网址 / .app / 文件 / 文件夹）："))
        h = QHBoxLayout()
        self.target_edit = QLineEdit(target)
        self.target_edit.setPlaceholderText("例如 http://127.0.0.1:5184/ 或 /Applications/xxx.app")
        h.addWidget(self.target_edit, 1)
        pick = QPushButton("选择文件…")
        pick.clicked.connect(self._pick)
        h.addWidget(pick)
        ow.addLayout(h)
        v.addWidget(self.open_widget)

        # —— 类型：模拟快捷键 ——
        self.keys_widget = QWidget()
        kw = QVBoxLayout(self.keys_widget)
        kw.setContentsMargins(0, 0, 0, 0)
        kw.addWidget(QLabel("组合键（点一下下面的框，直接在键盘上按出组合键即可，像其他软件那样）："))
        self.keyseq_edit = QKeySequenceEdit(combo_to_qkeysequence(keys))
        kw.addWidget(self.keyseq_edit)
        kw.addWidget(QLabel("修饰键写法：Cmd/Command、Ctrl/Control、Shift、Alt/Option、Win/Super。"
                           "主键写字符或名称（如 4、s、F5、Space、Esc、Left）。"))
        v.addWidget(self.keys_widget)

        v.addWidget(QLabel("提示：点一下组合键输入框，直接在键盘上按下组合键就会自动捕获；"
                           "模拟快捷键需 macOS 授予本程序「辅助功能」权限"
                           "（系统设置 → 隐私与安全性 → 辅助功能），否则按键会被系统忽略。"))

        btn = QHBoxLayout()
        ok = QPushButton("确定")
        ok.clicked.connect(self.accept)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        btn.addStretch(1)
        btn.addWidget(cancel)
        btn.addWidget(ok)
        v.addLayout(btn)

        self._on_type()

    def _on_type(self):
        is_keys = self.type_combo.currentData() == "keys"
        self.keys_widget.setVisible(is_keys)
        self.open_widget.setVisible(not is_keys)

    def _pick(self):
        start = os.path.expanduser((self.target_edit.text() or "~/Desktop").strip())
        path, _ = QFileDialog.getOpenFileName(self, "选择文件或程序", start)
        if path:
            self.target_edit.setText(path)

    def data(self):
        kind = self.type_combo.currentData()
        name = self.name_edit.text().strip()
        if kind == "keys":
            return (name, "", "keys", qkeysequence_to_combo(self.keyseq_edit.keySequence()))
        return (name, self.target_edit.text().strip(), "open", "")


class SettingsDialog(QDialog):
    def __init__(self, cfg, sources, floating, parent=None, all_sources=None):
        super().__init__(parent)
        self.cfg = cfg
        self.sources = sources
        self.floating = floating
        self.all_sources = all_sources or sources
        # 自定义右键菜单项（内存副本，确定时写回 cfg）
        self.custom_items = [dict(it) for it in (cfg.get("custom_items") or [])]
        # 记下打开对话框时的状态，「取消」时把实时预览的改动还原
        self._orig_transparency = int(cfg.get("transparency", 100))
        self._orig_size = clamp_icon_size(cfg.get("icon_size", ICON_SIZE_BASE))
        self.setWindowTitle("输入法悬浮球 · 设置")
        self.setMinimumWidth(420)
        self.setWindowFlags(
            (self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._build_ui()
        self._load_values()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # ---- 透明度 ----
        layout.addWidget(QLabel("整体透明度（100 级）"))
        row = QHBoxLayout()
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(1, 100)
        self.slider.setTickInterval(10)
        self.slider.valueChanged.connect(self._on_transparency)
        self.trans_label = QLabel()
        self.trans_label.setFixedWidth(48)
        row.addWidget(self.slider)
        row.addWidget(self.trans_label)
        layout.addLayout(row)

        # ---- 图标大小 ----
        layout.addWidget(QLabel("图标大小（直径，像素）"))
        size_row = QHBoxLayout()
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(ICON_SIZE_MIN, ICON_SIZE_MAX)
        self.size_slider.setTickInterval(10)
        self.size_slider.valueChanged.connect(self._on_size)
        self.size_label = QLabel()
        self.size_label.setFixedWidth(48)
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_label)
        layout.addLayout(size_row)

        quick = QHBoxLayout()
        for name, px in ICON_SIZE_PRESETS:
            b = QPushButton(f"{name} {px}")
            b.clicked.connect(lambda _, v=px: self.size_slider.setValue(v))
            quick.addWidget(b)
        quick.addStretch(1)
        layout.addLayout(quick)

        # ---- 背景 ----
        layout.addWidget(QLabel("图标背景"))
        bg_row = QHBoxLayout()
        self.btn_image = QPushButton("选择图片")
        self.btn_image.clicked.connect(self._choose_image)
        self.btn_clear = QPushButton("清除图片")
        self.btn_clear.clicked.connect(self._clear_image)
        self.btn_color = QPushButton("背景颜色")
        self.btn_color.clicked.connect(self._choose_color)
        self.bg_info = QLabel()
        bg_row.addWidget(self.btn_image)
        bg_row.addWidget(self.btn_clear)
        bg_row.addWidget(self.btn_color)
        bg_row.addWidget(self.bg_info, 1)
        layout.addLayout(bg_row)

        # ---- 参与切换的输入法 ----
        layout.addWidget(QLabel("左键循环切换以下输入法（勾选启用，顺序即循环顺序）"))
        self.listw = QListWidget()
        # 用与运行时一致的解析逻辑决定勾选状态：失效项会被自动纠正
        resolved = resolve_enabled(self.cfg["enabled"], self.sources, self.all_sources)
        enabled_ids = {s["id"] for s in resolved}
        for s in self.sources:
            item = QListWidgetItem(s["name"])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if s["id"] in enabled_ids
                               else Qt.CheckState.Unchecked)
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.listw.addItem(item)
        layout.addWidget(self.listw, 1)
        hint = QLabel("提示：至少勾选两个才能循环切换；只勾选一个等同于全选。")
        hint.setStyleSheet("color: #8a8a8a; font-size: 11px;")
        layout.addWidget(hint)

        # ---- 登录启动 ----
        self.chk_login = QCheckBox("登录系统时自动启动")
        layout.addWidget(self.chk_login)

        # ---- 狗蛋书签（集成到右键菜单）----
        layout.addWidget(QLabel("右键菜单「狗蛋书签」打开的程序 / 网页"))
        bm_row = QHBoxLayout()
        self.bm_app_edit = QLineEdit(self.cfg.get("bookmark_app") or "")
        self.bm_app_edit.setPlaceholderText("书签程序 .app 路径（留空则直接用下方网址）")
        bm_choose = QPushButton("选择…")
        bm_choose.clicked.connect(self._choose_bookmark_app)
        bm_row.addWidget(self.bm_app_edit, 1)
        bm_row.addWidget(bm_choose)
        layout.addLayout(bm_row)

        bm_row2 = QHBoxLayout()
        bm_row2.addWidget(QLabel("网页地址："))
        self.bm_url_edit = QLineEdit(self.cfg.get("bookmark_url") or "http://127.0.0.1:5184/")
        bm_row2.addWidget(self.bm_url_edit, 1)
        layout.addLayout(bm_row2)
        bm_hint = QLabel("说明：点击右键菜单「狗蛋书签」会启动该程序（需要时自动拉起本地服务）"
                         "并打开网页；程序不可用时直接用本地址兜底。")
        bm_hint.setStyleSheet("color: #8a8a8a; font-size: 11px;")
        bm_hint.setWordWrap(True)
        layout.addWidget(bm_hint)

        # ---- 右键菜单自定义快捷项 ----
        layout.addWidget(QLabel("右键菜单「我的快捷」自定义项（名字 / 链接自己填）"))
        self.custom_list = QListWidget()
        self.custom_list.setMinimumHeight(90)
        layout.addWidget(self.custom_list)
        cbtn = QHBoxLayout()
        b_add = QPushButton("添加")
        b_add.clicked.connect(self._add_custom)
        b_edit = QPushButton("编辑")
        b_edit.clicked.connect(self._edit_custom)
        b_del = QPushButton("删除")
        b_del.clicked.connect(self._del_custom)
        cbtn.addWidget(b_add)
        cbtn.addWidget(b_edit)
        cbtn.addWidget(b_del)
        cbtn.addStretch(1)
        layout.addLayout(cbtn)
        c_hint = QLabel("说明：这里添加的每一项都会出现在右键菜单（及托盘菜单）的「我的快捷」子菜单里，"
                        "点击即用默认方式打开你填的链接 / 程序 / 文件。")
        c_hint.setStyleSheet("color: #8a8a8a; font-size: 11px;")
        c_hint.setWordWrap(True)
        layout.addWidget(c_hint)
        self._fill_custom_list()

        # ---- 按钮 ----
        btn_row = QHBoxLayout()
        self.btn_ok = QPushButton("确定")
        self.btn_ok.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addStretch(1)
        btn_row.addWidget(self.btn_ok)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

    def _load_values(self):
        self.slider.setValue(int(self.cfg["transparency"]))
        self._on_transparency(self.cfg["transparency"])
        cur_size = clamp_icon_size(self.cfg.get("icon_size", ICON_SIZE_BASE))
        self.size_slider.setValue(cur_size)
        self._on_size(cur_size)
        if self.cfg["bg_image"]:
            self.bg_info.setText("图片：" + os.path.basename(self.cfg["bg_image"]))
        else:
            self.bg_info.setText("纯色：" + self.cfg["bg_color"])
        self.chk_login.setChecked(bool(self.cfg.get("login_start")))

    def _on_transparency(self, v):
        self.trans_label.setText(f"{v}%")
        self.cfg["transparency"] = v
        if self.floating:
            self.floating.setWindowOpacity(max(0.01, v / 100.0))
            self.floating._sync_note_transparency()  # 便签透明度实时跟随悬浮球

    def _on_size(self, v):
        v = clamp_icon_size(v)
        self.size_label.setText(f"{v}px")
        self.cfg["icon_size"] = v
        if self.floating:
            # 拖动时实时预览；落盘由「确定」触发的 save_config 统一完成
            self.floating.apply_icon_size(v)

    def _choose_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择图标背景图片", "",
            "图片 (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        if path:
            self.cfg["bg_image"] = path
            self.bg_info.setText("图片：" + os.path.basename(path))
            if self.floating:
                self.floating.load_bg()
                self.floating.update()

    def _clear_image(self):
        self.cfg["bg_image"] = ""
        self.bg_info.setText("纯色：" + self.cfg["bg_color"])
        if self.floating:
            self.floating.load_bg()
            self.floating.update()

    def _choose_color(self):
        init = QColor(self.cfg.get("bg_color") or "#3a7afe")
        col = QColorDialog.getColor(init, self, "选择背景颜色")
        if col.isValid():
            self.cfg["bg_color"] = col.name()
            self.bg_info.setText("纯色：" + self.cfg["bg_color"])
            if not self.cfg["bg_image"] and self.floating:
                self.floating.load_bg()
                self.floating.update()

    def _choose_bookmark_app(self):
        start = os.path.expanduser((self.bm_app_edit.text() or "~/Desktop").strip())
        path, _ = QFileDialog.getOpenFileName(
            self, "选择书签程序", start, "应用程序 (*.app)")
        if path:
            self.bm_app_edit.setText(path)

    def _fill_custom_list(self):
        self.custom_list.clear()
        for it in self.custom_items:
            kind = it.get("kind", "open")
            if kind == "keys":
                self.custom_list.addItem(
                    f"{it.get('name', '')}  ⌨ {it.get('keys', '')}  [快捷键]")
            else:
                self.custom_list.addItem(
                    f"{it.get('name', '')}  →  {it.get('target', '')}")

    def _commit_custom(self, name, target, kind, keys, row=None):
        if not name:
            return
        item = {"name": name, "kind": kind}
        if kind == "keys":
            if not keys:
                return
            item["keys"] = keys
        else:
            if not target:
                return
            item["target"] = target
        if row is None:
            self.custom_items.append(item)
        else:
            self.custom_items[row] = item
        self._fill_custom_list()

    def _add_custom(self):
        dlg = CustomItemDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, target, kind, keys = dlg.data()
            self._commit_custom(name, target, kind, keys)

    def _edit_custom(self):
        row = self.custom_list.currentRow()
        if row < 0 or row >= len(self.custom_items):
            return
        it = self.custom_items[row]
        dlg = CustomItemDialog(self, it.get("name", ""), it.get("target", ""),
                              it.get("kind", "open"), it.get("keys", ""))
        if dlg.exec() == QDialog.DialogCode.Accepted:
            name, target, kind, keys = dlg.data()
            self._commit_custom(name, target, kind, keys, row=row)

    def _del_custom(self):
        row = self.custom_list.currentRow()
        if row < 0 or row >= len(self.custom_items):
            return
        del self.custom_items[row]
        self._fill_custom_list()

    def accept(self):
        enabled = []
        for i in range(self.listw.count()):
            item = self.listw.item(i)
            if item.checkState() == Qt.CheckState.Checked:
                # 同时存名称：第三方输入法的 ID 会在父级/模式间变化，名称才是稳定标识
                enabled.append({"id": item.data(Qt.ItemDataRole.UserRole),
                                "name": item.text()})
        self.cfg["enabled"] = enabled
        self.cfg["login_start"] = self.chk_login.isChecked()
        self.cfg["transparency"] = int(self.slider.value())
        self.cfg["icon_size"] = clamp_icon_size(self.size_slider.value())
        self.cfg["bookmark_app"] = (self.bm_app_edit.text() or "").strip()
        self.cfg["bookmark_url"] = (self.bm_url_edit.text()
                                    or "http://127.0.0.1:5184/").strip()
        self.cfg["custom_items"] = [dict(it) for it in self.custom_items]
        save_config(self.cfg)
        set_login_item(self.cfg["login_start"])
        if self.floating:
            self.floating.apply_config()
        super().accept()

    def reject(self):
        # 「取消」把期间实时预览的透明度和大小还原回去
        self.cfg["transparency"] = self._orig_transparency
        self.cfg["icon_size"] = self._orig_size
        if self.floating:
            self.floating.setWindowOpacity(max(0.01, self._orig_transparency / 100.0))
            self.floating._sync_note_transparency()
            self.floating.apply_icon_size(self._orig_size, persist=True)
            self.floating.update()
        super().reject()


class FloatingIcon(QWidget):
    def __init__(self, cfg, sources, all_sources=None):
        super().__init__()
        self.cfg = cfg
        self.sources = sources            # 展示/参与切换的输入法（已过滤去重）
        self.all_sources = all_sources or sources  # 原始全量（用于标签映射）
        self.icon_size = clamp_icon_size(cfg.get("icon_size", ICON_SIZE_BASE))
        self.cfg["icon_size"] = self.icon_size
        self.dragging = False
        self.press_global = None
        self._bg_pixmap = None
        self.current_label = ""

        flags = (Qt.WindowType.FramelessWindowHint |
                 Qt.WindowType.WindowStaysOnTopHint)
        if IS_WIN:
            # Windows 上再加 Tool：不在任务栏占位、不抢 Alt+Tab。
            # macOS 上不能加（会把置顶层级压下去），故按平台区分。
            flags |= Qt.WindowType.Tool
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.icon_size, self.icon_size)
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        # 注意：不要用 setMouseTracking(True)——macOS 的 Qt cocoa 插件在处理
        # enter/exit 追踪事件时会调用 -[NSEvent clickCount] 并触发断言而崩溃。
        # 改用下面的定时器轮询光标位置来判断"悬停下边缘"，效果相同且稳定。
        self._hover_bottom = False
        self.setToolTip("输入法悬浮球 · 左键切换 / 点下边缘开便签 / 右键菜单 / 滚轮调透明度")

        self._restore_position()
        self.apply_config()
        self.refresh_label()
        self._sync_timer = QTimer(self)
        self._sync_timer.timeout.connect(self.refresh_label)
        self._sync_timer.start(800)
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._update_hover)
        self._hover_timer.start(200)

    # ----- 位置 -----
    def resizeEvent(self, event):
        # 尺寸变化时同步更新圆形遮罩（保证圆外点击穿透与形状正确）
        self.setMask(QRegion(self.rect(), QRegion.RegionType.Ellipse))
        super().resizeEvent(event)

    def _screen_rect(self, x, y):
        scr = QApplication.screenAt(QPoint(int(x), int(y))) or QApplication.primaryScreen()
        return scr.availableGeometry()

    def _clamp_pos(self, x, y):
        """把坐标夹到屏幕可见范围内。
        否则一旦被拖到（或从配置恢复到）屏幕外，球就"消失"了，
        现象和"程序打不开"一模一样。"""
        r = self._screen_rect(x, y)
        max_x = max(r.left(), r.right() - self.width() + 1)
        max_y = max(r.top(), r.bottom() - self.height() + 1)
        return (max(r.left(), min(int(x), max_x)),
                max(r.top(), min(int(y), max_y)))

    def _restore_position(self):
        pos = self.cfg.get("position")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            x, y = self._clamp_pos(int(pos[0]), int(pos[1]))
            self.move(x, y)
            if [x, y] != [int(pos[0]), int(pos[1])]:
                # 原位置在屏幕外，纠正后立即写回，避免下次再"消失"
                self.cfg["position"] = [x, y]
                save_config(self.cfg)
        else:
            sg = QApplication.primaryScreen().availableGeometry()
            x, y = self._clamp_pos(sg.right() - self.icon_size - 20, sg.top() + 60)
            self.move(x, y)

    # ----- 配置应用 -----
    def apply_config(self):
        self.setWindowOpacity(max(0.01, self.cfg["transparency"] / 100.0))
        self._sync_note_transparency()
        self.load_bg()
        self.update()

    def _sync_note_transparency(self):
        note = getattr(self, "_note", None)
        if note is not None:
            note.sync_transparency()

    def load_bg(self):
        self._bg_pixmap = None
        img = self.cfg.get("bg_image", "")
        if img and os.path.exists(img):
            pm = QPixmap(img)
            if not pm.isNull():
                self._bg_pixmap = pm.scaled(
                    self.icon_size, self.icon_size,
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                    Qt.TransformationMode.SmoothTransformation)

    def apply_icon_size(self, size, persist=False):
        """改变图标直径：以圆心为中心缩放，并夹进屏幕，避免放大后跑出可见区。"""
        size = clamp_icon_size(size)
        if size == self.icon_size:
            return
        center = self.geometry().center()
        self.icon_size = size
        self.cfg["icon_size"] = size
        self.setFixedSize(size, size)      # 触发 resizeEvent → 同步圆形遮罩
        self.move(center.x() - size // 2, center.y() - size // 2)
        x, y = self._clamp_pos(self.x(), self.y())
        self.move(x, y)
        self.cfg["position"] = [x, y]
        self.load_bg()                     # 背景图按新尺寸重新缩放
        if persist:
            save_config(self.cfg)
        self.update()

    # ----- 标签 -----
    def set_label(self, name):
        lbl = short_label(name)
        if lbl != self.current_label:
            self.current_label = lbl
            self.update()

    def refresh_label(self):
        cid = IMESwitch.current_id()
        if not cid:
            return
        for s in self.all_sources:
            if s["id"] == cid:
                self.set_label(s["name"])
                return
        # 当前是某个模式的子项，映射到其「父级」输入法名称
        for s in self.all_sources:
            if cid.startswith(s["id"] + ".") or s["id"].startswith(cid + "."):
                self.set_label(s["name"])
                return

    # ----- 绘制 -----
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = self.rect()
        cx, cy = rect.width() / 2.0, rect.height() / 2.0

        # 所有装饰参数都以基准尺寸 84 为参照等比缩放，改变图标大小时质感不变
        s = self.icon_size / float(ICON_SIZE_BASE)

        def sp(v, minimum=1.0):
            """scale pixel: 按比例缩放像素值，避免小尺寸下线条消失。"""
            return max(minimum, v * s)

        inset = int(round(sp(2)))          # 绘制圆相对窗口遮罩的内缩
        r = rect.width() / 2.0 - inset

        # 用矢量 QPainterPath 椭圆做抗锯齿裁剪（位图 QRegion 遮罩会有锯齿）。
        # 比窗口遮罩内缩 2px，使遮罩的硬边落在透明区、肉眼完全不可见；
        # 窗口遮罩仍保留，保证圆外区域点击穿透。
        circle = QPainterPath()
        circle.addEllipse(QRectF(rect.adjusted(inset, inset, -inset, -inset)))
        p.setClipPath(circle)

        # 背景：自定义图片 or 垂直渐变纯色（上亮下暗，营造玻璃质感）
        if self._bg_pixmap is not None:
            p.drawPixmap(rect, self._bg_pixmap)
        else:
            base = QColor(self.cfg.get("bg_color") or "#3a7afe")
            grad = QLinearGradient(0, rect.top(), 0, rect.bottom())
            grad.setColorAt(0.0, base.lighter(114))
            grad.setColorAt(0.55, base)
            grad.setColorAt(1.0, base.darker(116))
            p.fillRect(rect, QBrush(grad))

        # 边缘暗角（内阴影）：边缘轻微压暗，增加立体感，贴近系统图标
        vig = QRadialGradient(cx, cy, r)
        vig.setColorAt(0.0, QColor(0, 0, 0, 0))
        vig.setColorAt(0.80, QColor(0, 0, 0, 0))
        vig.setColorAt(1.0, QColor(0, 0, 0, 42))
        p.fillRect(rect, QBrush(vig))

        p.setClipping(False)
        # 顶部高光弧（玻璃反射的月牙，悬于上方、不贴边）
        hl = QPen(QColor(255, 255, 255, 150))
        hl.setWidthF(sp(4))
        hl.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(hl)
        p.setBrush(Qt.BrushStyle.NoBrush)
        a1 = int(round(sp(11)))
        p.drawArc(rect.adjusted(a1, a1, -a1, -a1), 38 * 16, 104 * 16)

        # 底部内阴影弧（增强球体立体感）
        sh = QPen(QColor(0, 0, 0, 38))
        sh.setWidthF(sp(4))
        sh.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(sh)
        a2 = int(round(sp(4)))
        p.drawArc(rect.adjusted(a2, a2, -a2, -a2), 218 * 16, 104 * 16)

        # 发丝级深色描边：1.5px 定义边缘，比粗白环更克制、更贴近系统图标
        rim = QPen(QColor(0, 0, 0, 90))
        rim.setWidthF(sp(1.5, 1.0))
        p.setPen(rim)
        p.drawEllipse(rect.adjusted(inset, inset, -inset, -inset))

        # 悬停在下边缘时的高亮提示（暗示此处可点开便签）
        if getattr(self, "_hover_bottom", False):
            hb = QPen(QColor(255, 255, 255, 190))
            hb.setWidthF(sp(2.5, 1.5))
            hb.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(hb)
            p.setBrush(Qt.BrushStyle.NoBrush)
            a3 = int(round(sp(6)))
            p.drawArc(rect.adjusted(a3, a3, -a3, -a3), 218 * 16, 104 * 16)

        # 中央文字（字号同样等比缩放）
        if self.current_label:
            p.setPen(QColor(255, 255, 255))
            f = QFont()
            f.setBold(True)
            ln = len(self.current_label)
            base_pt = 30 if ln <= 1 else (22 if ln <= 2 else 15)
            f.setPointSizeF(max(6.0, base_pt * s))
            p.setFont(f)
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.current_label)
        p.end()

    # ----- 鼠标 -----
    def _in_bottom_edge(self, pos):
        """判断点位是否落在圆的下边缘热区（此区域点击 = 打开便签）。"""
        rect = self.rect()
        cx, cy = rect.width() / 2.0, rect.height() / 2.0
        r = rect.width() / 2.0
        dx = pos.x() - cx
        dy = pos.y() - cy
        if dx * dx + dy * dy > r * r:   # 圆外不算
            return False
        return dy > r * 0.5             # 圆心下方约 25% 高度带

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.press_global = event.globalPosition().toPoint()
            self.dragging = False
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.press_global is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            gpos = event.globalPosition().toPoint()
            delta = gpos - self.press_global
            if delta.manhattanLength() > 4:
                self.dragging = True
            if self.dragging:
                self.move(self.pos() + delta)
                self.press_global = gpos
        super().mouseMoveEvent(event)

    def _update_hover(self):
        """定时器轮询：光标是否悬停在"下边缘"热区（替代 mouseTracking，避免崩溃）。"""
        if not self.isVisible():
            return
        over = self._in_bottom_edge(self.mapFromGlobal(QCursor.pos())) and not self.dragging
        if over != self._hover_bottom:
            self._hover_bottom = over
            self.update()

    def leaveEvent(self, event):
        if self._hover_bottom:
            self._hover_bottom = False
            self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.dragging:
                pos = event.position().toPoint()
                if self._in_bottom_edge(pos):
                    self.open_note()        # 下边缘 → 打开便签
                else:
                    self.switch_input()     # 其余区域 → 切换输入法
            else:
                x, y = self._clamp_pos(self.x(), self.y())
                if (x, y) != (self.x(), self.y()):
                    self.move(x, y)     # 拖出屏幕时拉回来
                self.cfg["position"] = [x, y]
                save_config(self.cfg)
            self.dragging = False
            self.press_global = None
        super().mouseReleaseEvent(event)

    def wheelEvent(self, event):
        d = event.angleDelta().y()
        step = 1 if d > 0 else -1
        self.cfg["transparency"] = max(1, min(100, self.cfg["transparency"] + step))
        self.setWindowOpacity(self.cfg["transparency"] / 100.0)
        self._sync_note_transparency()
        save_config(self.cfg)
        super().wheelEvent(event)

    def contextMenuEvent(self, event):
        menu = QMenu(self)
        a_switch = menu.addAction("切换输入法")
        a_settings = menu.addAction("设置...")
        a_note = menu.addAction("便签...")
        a_bookmark = menu.addAction("狗蛋书签")

        # 我的快捷（用户在「设置」里自行添加的自定义右键项）
        custom_menu = menu.addMenu("我的快捷")
        custom_acts = {}
        for it in (self.cfg.get("custom_items") or []):
            name = (it.get("name") or "未命名").strip() or "未命名"
            a = custom_menu.addAction(name)
            kind = it.get("kind", "open")
            val = it.get("keys", "") if kind == "keys" else it.get("target", "")
            custom_acts[a] = (kind, val)
        if not custom_acts:
            na = custom_menu.addAction("（去「设置」里添加）")
            na.setEnabled(False)

        # 图标大小快捷档位（也可在「设置」里用滑块无级调节）
        size_menu = menu.addMenu("图标大小")
        size_acts = {}
        for name, px in ICON_SIZE_PRESETS:
            a = size_menu.addAction(f"{name}（{px}px）")
            a.setCheckable(True)
            a.setChecked(px == self.icon_size)
            size_acts[a] = px
        size_menu.addSeparator()
        a_size_set = size_menu.addAction("更多…")

        a_hide = menu.addAction("隐藏")
        menu.addSeparator()
        a_quit = menu.addAction("退出")
        act = menu.exec(event.globalPos())
        if act == a_switch:
            self.switch_input()
        elif act == a_settings:
            self.open_settings()
        elif act == a_note:
            self.open_note()
        elif act == a_bookmark:
            self.open_bookmark()
        elif act in custom_acts:
            kind, val = custom_acts[act]
            if kind == "keys":
                send_key_combo(val)
            else:
                open_target(val)
        elif act in size_acts:
            self.apply_icon_size(size_acts[act], persist=True)
        elif act == a_size_set:
            self.open_settings()
        elif act == a_hide:
            self.hide()
        elif act == a_quit:
            QApplication.quit()

    # ----- 功能 -----
    def enabled_sources(self):
        return resolve_enabled(self.cfg["enabled"], self.sources, self.all_sources)

    def _select_source(self, disp):
        """切换到某个展示输入法：先试其 ID，失败则回退到其模式/同名的其它可选源。
        第三方输入法的父级 ID（如 com.tencent.inputmethod.wetype）常不可直接选中，
        只有 .pinyin 等模式可选，故需要回退，否则会「切过去就切不回」。"""
        candidates = []
        for s in self.all_sources:
            if (s["id"] == disp["id"]
                    or s["id"].startswith(disp["id"] + ".")
                    or s["name"] == disp["name"]):
                candidates.append(s["id"])
        order = []
        for cid in [disp["id"]] + candidates:  # 展示 ID 优先，再去重保序
            if cid and cid not in order:
                order.append(cid)
        for cid in order:
            if IMESwitch.select_id(cid):
                return True
        return False

    def switch_input(self):
        enabled = self.enabled_sources()
        if not enabled:
            return
        cur = IMESwitch.current_id()
        # 将「当前输入法」映射到启用的展示项（含模式/父级的互指）
        idx = -1
        for i, s in enumerate(enabled):
            if s["id"] == cur or cur.startswith(s["id"] + ".") or s["id"].startswith(cur + "."):
                idx = i
                break
        nxt = enabled[(idx + 1) % len(enabled)]
        if self._select_source(nxt):
            self.set_label(nxt["name"])
            self.refresh_label()

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self.sources, self, self, self.all_sources)
        dlg.exec()

    def open_note(self):
        if not hasattr(self, "_note") or self._note is None:
            # 独立顶层窗口：透明度才能独立于悬浮球生效
            self._note = NoteWindow(self.cfg)
        self._note.show()
        self._note.raise_()
        self._note.activateWindow()

    def open_bookmark(self):
        """从右键菜单打开「狗蛋书签」：
        · 优先启动其 .app（程序自身会按需拉起本地服务并打开浏览器），最稳妥；
        · 若未配置 .app 或启动失败，则直接打开网页地址兜底（需本地服务已在运行）。"""
        app = os.path.expanduser((self.cfg.get("bookmark_app") or "").strip())
        url = (self.cfg.get("bookmark_url") or "http://127.0.0.1:5184/").strip()
        if IS_MAC and app and os.path.isdir(app) and app.lower().endswith(".app"):
            try:
                subprocess.run(["open", "-a", app], check=False)
                return
            except Exception as e:
                print("启动书签程序失败，改用浏览器打开：", e, file=sys.stderr)
        if url:
            QDesktopServices.openUrl(QUrl(url))


# ---------------------------------------------------------------------------
# 3.5) 便签窗口（右键「便签」打开：透明度 / 自动保存 / 最近 3 版历史）
# ---------------------------------------------------------------------------
class NoteHistoryDialog(QDialog):
    def __init__(self, history, parent=None):
        super().__init__(parent)
        self.history = history
        self.restored = None
        self.setWindowTitle("便签历史（最近 3 版）")
        self.setMinimumWidth(440)
        self.setWindowFlags(
            (self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
            & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        if not self.history:
            layout.addWidget(QLabel("暂无历史版本。"))
        else:
            for i, item in enumerate(self.history):
                t = item.get("time", "")
                c = item.get("content", "") or ""
                preview = (c[:80] + ("…" if len(c) > 80 else "")) if c else "（空）"
                row = QHBoxLayout()
                label = QLabel(f"版本 {len(self.history) - i}　{t}\n{preview}")
                label.setWordWrap(True)
                row.addWidget(label, 1)
                btn = QPushButton("恢复")
                btn.clicked.connect(lambda _, idx=i: self._restore(idx))
                row.addWidget(btn)
                layout.addLayout(row)
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _restore(self, idx):
        self.restored = self.history[idx].get("content", "")
        self.accept()


class NoteWindow(QWidget):
    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.resize(260, 240)
        self._dragging = False
        self._drag_pos = None
        self._build_ui()
        self._restore_position()
        self.sync_transparency()
        self._editor.setPlainText(load_note())
        # 即时自动保存 + 空闲时记录历史版本
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self._autosave)
        self._idle_timer = QTimer(self)
        self._idle_timer.setSingleShot(True)
        self._idle_timer.timeout.connect(self._milestone)
        self._editor.textChanged.connect(self._on_text_changed)
        # 应用退出时强制保存一次，避免最后 500ms 内的输入丢失
        qapp = QApplication.instance()
        if qapp is not None:
            qapp.aboutToQuit.connect(self.force_save)

    def _build_ui(self):
        self._swatches = []
        root = QFrame(self)
        self.root = root
        root.setObjectName("noteRoot")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 头部：拖拽 + 关闭（加大关闭按钮，便于点击）
        header = QFrame(root)
        header.setObjectName("noteHeader")
        header.setFixedHeight(38)
        hbox = QHBoxLayout(header)
        hbox.setContentsMargins(0, 0, 4, 0)
        title = QLabel("便签", header)
        title.setObjectName("noteTitle")
        close_btn = QPushButton("×", header)
        close_btn.setObjectName("noteClose")
        close_btn.setFixedSize(46, 34)
        close_btn.setToolTip("收起便签")
        close_btn.clicked.connect(self.hide)
        hbox.addWidget(title)
        hbox.addStretch(1)
        hbox.addWidget(close_btn)
        layout.addWidget(header)

        # 正文
        self._editor = QTextEdit(root)
        self._editor.setPlaceholderText("写点什么…（自动保存）")
        layout.addWidget(self._editor, 1)

        # 底部：透明度 + 历史 + 颜色
        footer = QFrame(root)
        footer.setObjectName("noteFooter")
        fbox = QVBoxLayout(footer)
        fbox.setContentsMargins(8, 5, 8, 6)
        fbox.setSpacing(5)

        row1 = QHBoxLayout()
        trans_label = QLabel("透明度：随悬浮球", footer)
        trans_label.setObjectName("noteTransLabel")
        hist_btn = QPushButton("历史", footer)
        hist_btn.setObjectName("noteHistory")
        hist_btn.clicked.connect(self.open_history)
        row1.addWidget(trans_label)
        row1.addStretch(1)
        row1.addWidget(hist_btn)
        fbox.addLayout(row1)

        row2 = QHBoxLayout()
        color_label = QLabel("颜色", footer)
        color_label.setObjectName("noteColorLabel")
        row2.addWidget(color_label)
        for c in NOTE_PRESET_COLORS:
            b = QPushButton(footer)
            b.setObjectName("noteSwatch")
            b.setFixedSize(22, 22)
            b.setToolTip(c)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _, cc=c: self._set_note_color(cc))
            self._swatches.append((b, c))
            row2.addWidget(b)
        row2.addStretch(1)
        more_btn = QPushButton("更多…", footer)
        more_btn.setObjectName("noteMore")
        more_btn.clicked.connect(self._choose_color)
        row2.addWidget(more_btn)
        fbox.addLayout(row2)

        layout.addWidget(footer)

        self._header = header
        self._apply_theme()
        self._refresh_swatch_borders()

    def _apply_theme(self):
        base = QColor(self.cfg.get("note_color") or "#fff6c9")
        border = base.darker(125).name()
        header_bg = base.darker(106).name()
        footer_bg = base.darker(108).name()
        hover = base.darker(118).name()
        self.root.setStyleSheet(f"""
            QFrame#noteRoot {{ background: {base.name()}; border: 1px solid {border}; }}
            QFrame#noteHeader {{ background: {header_bg}; border-bottom: 1px solid {border}; }}
            QLabel#noteTitle {{ color: #4a4030; font-weight: bold; padding: 6px 10px; }}
            QPushButton#noteClose {{
                background: {header_bg}; color: #4a4030; border: none;
                font-size: 20px; border-radius: 7px; padding: 0 2px;
            }}
            QPushButton#noteClose:hover {{ background: {hover}; }}
            QTextEdit {{
                background: transparent; color: #2f2b22;
                border: none; padding: 8px; font-size: 14px;
            }}
            QFrame#noteFooter {{ background: {footer_bg}; border-top: 1px solid {border}; }}
            QLabel#noteTransLabel, QLabel#noteColorLabel {{ color: #4a4030; padding: 0 4px; }}
            QPushButton#noteHistory, QPushButton#noteMore {{
                background: {header_bg}; color: #4a4030;
                border: 1px solid {border}; border-radius: 5px; padding: 2px 10px;
            }}
            QPushButton#noteHistory:hover, QPushButton#noteMore:hover {{ background: {hover}; }}
        """)

    def _refresh_swatch_borders(self):
        cur = (self.cfg.get("note_color") or "").lower()
        for b, c in self._swatches:
            active = (c.lower() == cur)
            border = "2px solid #7a6a2a" if active else "1px solid rgba(0,0,0,0.25)"
            b.setStyleSheet(
                f"QPushButton#noteSwatch {{ background: {c}; border: {border}; border-radius: 7px; }}")

    def _set_note_color(self, hexcolor):
        self.cfg["note_color"] = hexcolor
        save_config(self.cfg)
        self._apply_theme()
        self._refresh_swatch_borders()

    def _choose_color(self):
        init = QColor(self.cfg.get("note_color") or "#fff6c9")
        col = QColorDialog.getColor(init, self, "选择便签颜色")
        if col.isValid():
            self._set_note_color(col.name())

    def _restore_position(self):
        pos = self.cfg.get("note_position")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            self.move(int(pos[0]), int(pos[1]))
        else:
            sg = QApplication.primaryScreen().availableGeometry()
            self.move(sg.left() + 60, sg.top() + 60)

    def sync_transparency(self):
        """便签透明度跟随悬浮球（共用同一个 transparency 设置）。"""
        v = int(self.cfg.get("transparency", 100))
        self.setWindowOpacity(max(0.01, v / 100.0))

    # ----- 自动保存 / 历史 -----
    def _on_text_changed(self):
        self._save_timer.start(500)
        self._idle_timer.start(5000)

    def _autosave(self):
        save_note(self._editor.toPlainText())

    def _milestone(self):
        text = self._editor.toPlainText()
        hist = load_note_history()
        if hist and hist[0].get("content") == text:
            return  # 与最新历史相同，不重复记录
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        hist.insert(0, {"time": now, "content": text})
        del hist[NOTE_HISTORY_MAX:]
        save_note_history(hist)

    def open_history(self):
        dlg = NoteHistoryDialog(load_note_history(), self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.restored is not None:
            self._editor.setPlainText(dlg.restored)
            self._autosave()
            self._milestone()

    # ----- 拖拽（仅头部可拖）-----
    def mousePressEvent(self, event):
        if (event.button() == Qt.MouseButton.LeftButton
                and self._header.geometry().contains(event.pos())):
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            g = event.globalPosition().toPoint()
            self.move(self.pos() + g - self._drag_pos)
            self._drag_pos = g
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self.cfg["note_position"] = [self.x(), self.y()]
            save_config(self.cfg)
        super().mouseReleaseEvent(event)

    def hideEvent(self, event):
        # 每次隐藏（点 × 或退出）都保存内容、记录历史、保存位置
        self._autosave()
        self._milestone()
        self.cfg["note_position"] = [self.x(), self.y()]
        save_config(self.cfg)
        super().hideEvent(event)

    def force_save(self):
        self._autosave()
        self._milestone()
        self.cfg["note_position"] = [self.x(), self.y()]
        save_config(self.cfg)


# ---------------------------------------------------------------------------
# 4) 开机自启（macOS: LaunchAgent / Windows: 启动文件夹快捷方式）
# ---------------------------------------------------------------------------
def _win_startup_lnk():
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(appdata, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup", "输入法悬浮球.lnk")


def set_login_item_win(enable):
    """Windows 绿色版开机自启：只在「启动」文件夹里创建/删除一个快捷方式，
    不碰注册表。用 PowerShell 的 WScript.Shell COM 生成 .lnk（系统自带，无需额外依赖）。"""
    lnk = _win_startup_lnk()
    try:
        if not enable:
            if os.path.exists(lnk):
                os.remove(lnk)
            return
        os.makedirs(os.path.dirname(lnk), exist_ok=True)
        if getattr(sys, "frozen", False):
            target, args, workdir = sys.executable, "", os.path.dirname(sys.executable)
        else:
            target = sys.executable
            args = '"%s"' % os.path.abspath(__file__)
            workdir = os.path.dirname(os.path.abspath(__file__))
        ps = (
            "$ws = New-Object -ComObject WScript.Shell; "
            "$s = $ws.CreateShortcut('%s'); "
            "$s.TargetPath = '%s'; "
            "$s.Arguments = '%s'; "
            "$s.WorkingDirectory = '%s'; "
            "$s.WindowStyle = 7; "
            "$s.Save()"
        ) % (lnk.replace("'", "''"), target.replace("'", "''"),
             args.replace("'", "''"), workdir.replace("'", "''"))
        subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                        "-Command", ps],
                       capture_output=True, timeout=20)
    except Exception as e:
        print("设置开机自启失败：", e, file=sys.stderr)


def set_login_item(enable):
    if IS_WIN:
        set_login_item_win(enable)
        return
    plist_path = os.path.expanduser("~/Library/LaunchAgents/com.imefloat.plist")
    if enable:
        os.makedirs(os.path.dirname(plist_path), exist_ok=True)
        # 打包成 .app 后 sys.executable 在 .app 内部、__file__ 不可靠；
        # 改用 `open -a <app>` 启动；脚本方式仍用 python3 + 脚本路径。
        if getattr(sys, "frozen", False):
            _exe = sys.executable  # .../Xxx.app/Contents/MacOS/Xxx
            _app = os.path.dirname(os.path.dirname(os.path.dirname(_exe)))
            args = ["/usr/bin/open", "-a", _app]
        else:
            args = [sys.executable, os.path.abspath(__file__)]
        arg_xml = "\n".join(f"        <string>{a}</string>" for a in args)
        content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.imefloat</string>
    <key>ProgramArguments</key>
    <array>
{arg_xml}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>ProcessType</key>
    <string>Interactive</string>
</dict>
</plist>
'''
        try:
            with open(plist_path, "w", encoding="utf-8") as f:
                f.write(content)
            subprocess.run(["launchctl", "load", plist_path], capture_output=True)
        except Exception as e:
            print("设置登录启动失败：", e, file=sys.stderr)
    else:
        try:
            subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
        except Exception:
            pass
        try:
            os.remove(plist_path)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 5) 主入口
# ---------------------------------------------------------------------------
def acquire_single_instance():
    """尽力保证只有一个悬浮球实例。
    发现正在运行的旧实例：发送 'quit' 让其退出，等待其退出后接管；
    清理残留 socket 后监听。任何异常都返回 None（不阻塞启动）。
    返回一个 QLocalServer 实例（或 None）。"""
    try:
        from PyQt6.QtNetwork import QLocalServer, QLocalSocket
        import time as _time
        name = "InputMethodFloatBallSingleton"
        probe = QLocalSocket()
        probe.connectToServer(name)
        alive = probe.waitForConnected(150)
        probe.abort()
        if alive:
            sock = QLocalSocket()
            sock.connectToServer(name)
            if sock.waitForConnected(150):
                sock.write(b"quit")
                sock.flush()
                sock.waitForBytesWritten(150)
                sock.disconnectFromServer()
            for _ in range(30):  # 最多等 1.5s 让旧实例退出
                _time.sleep(0.05)
                p = QLocalSocket()
                p.connectToServer(name)
                still = p.waitForConnected(60)
                p.abort()
                if not still:
                    break
        server = QLocalServer()
        QLocalServer.removeServer(name)  # 清理可能残留的 socket 文件
        if not server.listen(name):
            server.listen(name + "-" + str(os.getpid()))
        return server
    except Exception:
        return None


def main():
    if not (IS_MAC or IS_WIN):
        print("本工具仅支持 macOS / Windows。", file=sys.stderr)
        return

    # 必须在 QApplication 创建之前设置：作为「辅助类」应用运行，不占用程序坞与菜单栏
    # （只有 macOS 有这个属性，Windows 上设置无意义）
    if IS_MAC:
        try:
            QApplication.setAttribute(Qt.ApplicationAttribute.AA_PluginApplication)
        except Exception:
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    # 单实例保护：发现旧实例则让其退出并接管，保证干净的单实例
    server = acquire_single_instance()

    cfg = load_config()
    raw = IMESwitch.list_sources()
    if not raw:
        QMessageBox.critical(
            None, "错误",
            "未能枚举到任何输入法。\n"
            "请确认系统里至少安装了一种输入法 / 键盘布局后重试。")
        return
    sources = get_display_sources(raw)

    floating = FloatingIcon(cfg, sources, raw)
    floating.show()
    floating.raise_()          # 确保置顶并可交互
    floating.activateWindow()

    # 托盘图标（隐藏后可从此恢复）
    tray_icon = QIcon(make_circle_pixmap(32, cfg.get("bg_color") or "#3a7afe"))
    tray = QSystemTrayIcon(tray_icon, app)
    tray.setToolTip("输入法悬浮球")
    tray_menu = QMenu()
    a_show = tray_menu.addAction("显示悬浮球")
    a_settings = tray_menu.addAction("设置...")
    a_note = tray_menu.addAction("便签...")
    a_bookmark = tray_menu.addAction("狗蛋书签")

    # 我的快捷（用户在「设置」里自行添加的自定义右键项）
    custom_menu = tray_menu.addMenu("我的快捷")
    custom_acts = {}
    for it in (cfg.get("custom_items") or []):
        name = (it.get("name") or "未命名").strip() or "未命名"
        a = custom_menu.addAction(name)
        kind = it.get("kind", "open")
        val = it.get("keys", "") if kind == "keys" else it.get("target", "")
        custom_acts[a] = (kind, val)
    if not custom_acts:
        na = custom_menu.addAction("（去「设置」里添加）")
        na.setEnabled(False)

    tray_menu.addSeparator()
    a_quit = tray_menu.addAction("退出")

    # 关键：macOS 上绝对不要用 tray.setContextMenu()。
    # Qt 6.11 的 QCocoaSystemTrayIcon 在设置上下文菜单时会注册「NSMenu 开始跟踪」
    # 通知的观察者（qcocoasystemtrayicon.mm: statusItemMenuBeganTracking:），
    # 其中直接读取 -[NSEvent clickCount]；而 macOS 14+ 菜单栏图标的菜单已改为
    # 跨进程跟踪，此刻 [NSApp currentEvent] 并不是鼠标事件 → NSAssertion 断言
    # → abort() 崩溃（Qt 6.12 才修复）。改为点击时自己弹出同一个 QMenu，
    # 功能完全一致，且不触发那条崩溃路径。
    if sys.platform == "darwin":
        tray.setContextMenu(None)
    else:
        tray.setContextMenu(tray_menu)
    tray.show()

    def on_show():
        floating.show()
        floating.raise_()
        floating.activateWindow()

    def _popup_tray_menu():
        if tray_menu.isVisible():
            return
        tray_menu.popup(QCursor.pos())

    def on_tray_activate(reason):
        R = QSystemTrayIcon.ActivationReason
        if reason == R.DoubleClick:
            on_show()
        elif sys.platform == "darwin" and reason in (R.Trigger, R.Context):
            # 兜底：万一菜单没弹出来，至少把被隐藏的球找回来
            if not floating.isVisible():
                on_show()
            # 状态栏按钮的动作是在 mouseDown 时发出的，立刻 popup 会被紧随的
            # mouseUp 立刻关掉，所以延迟 150ms 等按键抬起后再弹出菜单。
            QTimer.singleShot(150, _popup_tray_menu)

    tray.activated.connect(on_tray_activate)
    a_show.triggered.connect(on_show)
    a_settings.triggered.connect(floating.open_settings)
    a_note.triggered.connect(floating.open_note)
    a_bookmark.triggered.connect(floating.open_bookmark)
    for _a, _kv in custom_acts.items():
        _kind, _val = _kv
        if _kind == "keys":
            _a.triggered.connect(lambda _checked=False, c=_val: send_key_combo(c))
        else:
            _a.triggered.connect(lambda _checked=False, tgt=_val: open_target(tgt))
    a_quit.triggered.connect(QApplication.quit)

    # 单实例消息处理：'quit' 退出本实例；其它（如 'raise'）唤起悬浮球/便签
    if server is not None:
        def _on_new_conn():
            conn = server.nextPendingConnection()
            if conn is None:
                return
            try:
                conn.waitForReadyRead(150)
                data = bytes(conn.readAll()).decode("utf-8", "ignore") if conn.bytesAvailable() else ""
            except Exception:
                data = ""
            if data.strip() == "quit":
                conn.disconnectFromServer()
                QApplication.quit()
            else:
                on_show()
                note = getattr(floating, "_note", None)
                if note is not None:
                    note.show()
                    note.raise_()
                conn.disconnectFromServer()
        try:
            server.newConnection.connect(_on_new_conn)
        except Exception:
            pass


    sys.exit(app.exec())


if __name__ == "__main__":
    main()
