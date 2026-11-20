#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟键盘快捷键（纯 ctypes，无第三方依赖）
========================================
把形如 "Cmd+Shift+4" / "Ctrl+Shift+S" / "Win+Shift+S" 的组合，
按平台用系统原生接口真实「按下 / 抬起」发送出去，
从而触发系统或应用的快捷键（例如系统截图）。

  · macOS   → CoreGraphics 的 CGEvent（CGEventCreateKeyboardEvent / CGEventPost）
  · Windows → user32 的 SendInput

注意：macOS 上发送合成按键需要给本程序授予「辅助功能」权限
（系统设置 → 隐私与安全性 → 辅助功能，勾选输入法悬浮球）；
否则事件会被系统静默丢弃。Windows 一般不需要特殊权限。
"""

import sys

IS_WIN = sys.platform.startswith("win")
IS_MAC = sys.platform == "darwin"

# ---------------------------------------------------------------------------
# 组合键解析
# ---------------------------------------------------------------------------
MOD_WORDS = {
    "cmd", "command", "ctrl", "control", "shift", "alt", "option",
    "win", "super", "meta", "windows",
}


def parse_combo(combo):
    """解析 "Cmd+Shift+4" / "Ctrl+Shift+S" 之类，返回 (mods:set, key:str)。
    返回 None 表示无法解析（没有主键）。"""
    if not combo:
        return None
    parts = [p.strip().lower() for p in combo.replace("，", "+").split("+") if p.strip()]
    if not parts:
        return None
    mods = set()
    key = None
    for p in parts:
        if p in MOD_WORDS:
            mods.add(p)
        else:
            key = p  # 取最后一个非修饰键作主键
    if key is None:
        return None
    return mods, key


# ---------------------------------------------------------------------------
# macOS 实现（CoreGraphics）
# ---------------------------------------------------------------------------
# macOS 虚拟键码（常用）
MAC_KEYCODES = {
    'a': 0x00, 'b': 0x0B, 'c': 0x08, 'd': 0x02, 'e': 0x0E, 'f': 0x03,
    'g': 0x05, 'h': 0x04, 'i': 0x22, 'j': 0x26, 'k': 0x28, 'l': 0x25,
    'm': 0x2E, 'n': 0x2D, 'o': 0x1F, 'p': 0x23, 'q': 0x0C, 'r': 0x0F,
    's': 0x01, 't': 0x11, 'u': 0x20, 'v': 0x09, 'w': 0x0D, 'x': 0x07,
    'y': 0x10, 'z': 0x06,
    '0': 0x1D, '1': 0x12, '2': 0x13, '3': 0x14, '4': 0x15, '5': 0x17,
    '6': 0x16, '7': 0x1A, '8': 0x1C, '9': 0x19,
    'return': 0x24, 'enter': 0x24, 'tab': 0x30, 'space': 0x31,
    'backspace': 0x33, 'delete': 0x33, 'esc': 0x35, 'escape': 0x35,
    'f1': 0x7A, 'f2': 0x78, 'f3': 0x63, 'f4': 0x76, 'f5': 0x60,
    'f6': 0x61, 'f7': 0x62, 'f8': 0x64, 'f9': 0x65, 'f10': 0x6D,
    'f11': 0x67, 'f12': 0x6F,
    'left': 0x7B, 'right': 0x7C, 'down': 0x7D, 'up': 0x7E,
    'home': 0x73, 'end': 0x77, 'pageup': 0x74, 'pagedown': 0x79,
}
MAC_MOD_KEYCODES = {
    'command': 0x37, 'cmd': 0x37, 'shift': 0x38, 'option': 0x3A,
    'alt': 0x3A, 'control': 0x3B, 'ctrl': 0x3B,
}
# kCGEventFlagMask*（macOS 64 位事件标志）
MAC_MOD_FLAGS = {
    'command': 0x100000, 'cmd': 0x100000, 'shift': 0x20000,
    'option': 0x80000, 'alt': 0x80000, 'control': 0x40000, 'ctrl': 0x40000,
}

_mac_cg = None
_mac_warned_accessibility = False


def _mac_load_cg():
    global _mac_cg
    if _mac_cg is not None:
        return _mac_cg
    from ctypes import cdll, c_void_p, c_uint16, c_uint64, c_bool, c_int
    cg = cdll.LoadLibrary(
        "/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics")
    cg.CGEventCreateKeyboardEvent.restype = c_void_p
    cg.CGEventCreateKeyboardEvent.argtypes = [c_void_p, c_uint16, c_bool]
    cg.CGEventSetFlags.argtypes = [c_void_p, c_uint64]
    cg.CGEventPost.argtypes = [c_int, c_void_p]
    _mac_cg = cg
    return cg


def mac_has_accessibility():
    """本进程是否已被授予「辅助功能」信任（无法检测时返回 True 避免误报）。"""
    try:
        from ctypes import cdll, c_bool
        asr = cdll.LoadLibrary(
            "/System/Library/Frameworks/ApplicationServices.framework/"
            "ApplicationServices")
        fn = asr.AXIsProcessTrusted
        fn.restype = c_bool
        fn.argtypes = []
        return bool(fn())
    except Exception:
        return True


def send_key_combo_mac(mods, key):
    global _mac_warned_accessibility
    if not mac_has_accessibility():
        if not _mac_warned_accessibility:
            _mac_warned_accessibility = True
            try:
                from PyQt6.QtWidgets import QMessageBox
                QMessageBox.information(
                    None, "需要辅助功能权限",
                    "模拟系统快捷键需要授予「输入法悬浮球」辅助功能权限：\n\n"
                    "系统设置 → 隐私与安全性 → 辅助功能\n"
                    "在列表中勾选「输入法悬浮球」（或本 .app），然后重新点击。")
            except Exception:
                pass
        # 仍然尝试发送，万一行得通
    cg = _mac_load_cg()
    kc = MAC_KEYCODES.get(key.lower())
    if kc is None and len(key) == 1:
        kc = MAC_KEYCODES.get(key.lower())
    if kc is None:
        print("hotkey: 未知按键（macOS）：", key, file=sys.stderr)
        return
    flags = 0
    for m in mods:
        flags |= MAC_MOD_FLAGS.get(m, 0)
    mod_kcs = [MAC_MOD_KEYCODES[m] for m in mods if m in MAC_MOD_KEYCODES]

    # 按下修饰键
    for mkc in mod_kcs:
        ev = cg.CGEventCreateKeyboardEvent(None, mkc, True)
        cg.CGEventSetFlags(ev, flags)
        cg.CGEventPost(0, ev)  # 0 = kCGHIDEventTap
    # 按下主键
    ev = cg.CGEventCreateKeyboardEvent(None, kc, True)
    cg.CGEventSetFlags(ev, flags)
    cg.CGEventPost(0, ev)
    # 抬起主键
    ev = cg.CGEventCreateKeyboardEvent(None, kc, False)
    cg.CGEventSetFlags(ev, flags)
    cg.CGEventPost(0, ev)
    # 抬起修饰键（逆序）
    for mkc in reversed(mod_kcs):
        ev = cg.CGEventCreateKeyboardEvent(None, mkc, False)
        cg.CGEventSetFlags(ev, 0)
        cg.CGEventPost(0, ev)


# ---------------------------------------------------------------------------
# Windows 实现（user32.SendInput）
# ---------------------------------------------------------------------------
WIN_MOD = {
    'control': 0x11, 'ctrl': 0x11, 'shift': 0x10, 'alt': 0x12, 'menu': 0x12,
    'win': 0x5B, 'super': 0x5B, 'meta': 0x5B, 'windows': 0x5B,
}
WIN_VK = {
    'return': 0x0D, 'enter': 0x0D, 'tab': 0x09, 'space': 0x20,
    'backspace': 0x08, 'delete': 0x2E, 'esc': 0x1B, 'escape': 0x1B,
    'insert': 0x2D, 'home': 0x24, 'end': 0x23, 'pageup': 0x21,
    'pagedown': 0x22,
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73, 'f5': 0x74, 'f6': 0x75,
    'f7': 0x76, 'f8': 0x77, 'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    'left': 0x25, 'up': 0x26, 'right': 0x27, 'down': 0x28,
}


def send_key_combo_win(mods, key):
    import ctypes
    from ctypes import wintypes, c_ulong, POINTER, DWORD, WORD, LONG, BOOL

    user32 = ctypes.windll.user32

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                    ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD),
                    ("dwExtraInfo", POINTER(c_ulong))]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", POINTER(c_ulong))]

    class HARDWAREINPUT(ctypes.Structure):
        _fields_ = [("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD),
                    ("wParamH", wintypes.WORD)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]

    class INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("union", _INPUTUNION)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    # 主键虚拟键码
    if len(key) == 1 and key.isalnum():
        vk_main = ord(key.upper())
    else:
        vk_main = WIN_VK.get(key.lower())
    if vk_main is None:
        try:
            vk_main = ord(key) if len(key) == 1 else None
        except Exception:
            vk_main = None
    if vk_main is None:
        print("hotkey: 未知按键（Windows）：", key, file=sys.stderr)
        return

    mod_vks = [WIN_MOD[m] for m in mods if m in WIN_MOD]

    def kb(vk, up=False):
        ki = KEYBDINPUT(wVk=vk, wScan=0,
                        dwFlags=(KEYEVENTF_KEYUP if up else 0),
                        time=0, dwExtraInfo=None)
        return INPUT(type=INPUT_KEYBOARD, union=_INPUTUNION(ki=ki))

    events = []
    for vk in mod_vks:
        events.append(kb(vk, False))
    events.append(kb(vk_main, False))
    events.append(kb(vk_main, True))
    for vk in reversed(mod_vks):
        events.append(kb(vk, True))

    arr = (INPUT * len(events))(*events)
    user32.SendInput(len(events), ctypes.byref(arr), ctypes.sizeof(INPUT))


# ---------------------------------------------------------------------------
# 统一入口
# ---------------------------------------------------------------------------
def send_key_combo(combo):
    """发送一个键盘组合。combo 形如 "Cmd+Shift+4" / "Ctrl+Shift+S"。
    解析失败或平台不支持时打印到 stderr。"""
    parsed = parse_combo(combo)
    if not parsed:
        print("hotkey: 无法解析快捷键：", repr(combo), file=sys.stderr)
        return
    mods, key = parsed
    if IS_MAC:
        send_key_combo_mac(mods, key)
    elif IS_WIN:
        send_key_combo_win(mods, key)
    else:
        print("hotkey: 当前平台不支持模拟快捷键：", sys.platform, file=sys.stderr)


if __name__ == "__main__":
    # 调试用：python3 hotkey.py "Cmd+Shift+4"
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("combo")
    args = ap.parse_args()
    send_key_combo(args.combo)
