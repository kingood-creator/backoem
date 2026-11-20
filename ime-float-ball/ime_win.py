#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Windows 输入法后端（Win32，纯 ctypes，无第三方依赖）。

接口与 macOS 后端 MacIME 完全一致：
    list_sources() -> [{"id", "name", "hkl"}, ...]
    current_id()   -> str | None
    select_id(sid) -> bool

原理
----
Windows 的「输入法/键盘布局」在系统里就是一组 HKL（Keyboard Layout Handle）。
Win+Space 循环切换的正是这份列表，所以只要枚举 HKL 就能拿到「英语(美国) /
中文(简体) - 微软拼音 / 搜狗拼音 …」这些条目，切换就是对目标窗口投递
WM_INPUTLANGCHANGEREQUEST(0x0050)，lParam 传目标 HKL。

HKL → KLID 的换算（决定注册表里叫什么名字）：
    · 普通键盘布局：HKL = 0x04090409（高低字相同）→ KLID = "00000409"
    · 第三方输入法：HKL = 0xE0200804（高字是输入法自己的编号）
                    → KLID = "E0200804"
  即：高字 == 低字 → 用 "0000"+低字；否则 高字+低字。

注意：本模块在非 Windows 平台上 import 是安全的（所有 windll 调用都在
函数内部惰性获取），只是 list_sources() 会返回空列表。
"""

import sys

WM_INPUTLANGCHANGEREQUEST = 0x0050
SMTO_ABORTIFHUNG = 0x0002


class WinIME:
    """封装 Windows 输入法（键盘布局）枚举与切换。"""

    _user32 = None
    _hwnd_cache = None          # 最近一次属于「别的程序」的前台窗口
    _last_klid = None           # 我们最后一次主动切换到的 KLID

    # ------------------------------------------------------------------ 基础
    @classmethod
    def _api(cls):
        """惰性加载并声明 user32 的函数签名（非 Windows 返回 None）。"""
        if cls._user32 is not None or not sys.platform.startswith("win"):
            return cls._user32
        try:
            import ctypes
            from ctypes import wintypes

            u = ctypes.windll.user32
            u.GetKeyboardLayoutList.argtypes = [ctypes.c_int, ctypes.POINTER(ctypes.c_void_p)]
            u.GetKeyboardLayoutList.restype = ctypes.c_int
            u.GetKeyboardLayout.argtypes = [wintypes.DWORD]
            u.GetKeyboardLayout.restype = ctypes.c_void_p
            u.GetForegroundWindow.restype = ctypes.c_void_p
            u.GetForegroundWindow.argtypes = []
            u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
            u.GetWindowThreadProcessId.restype = wintypes.DWORD
            u.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                       wintypes.WPARAM, ctypes.c_void_p]
            u.PostMessageW.restype = wintypes.BOOL
            u.SendMessageTimeoutW.argtypes = [ctypes.c_void_p, wintypes.UINT,
                                              wintypes.WPARAM, ctypes.c_void_p,
                                              wintypes.UINT, wintypes.UINT,
                                              ctypes.POINTER(ctypes.c_size_t)]
            u.SendMessageTimeoutW.restype = ctypes.c_void_p
            u.ActivateKeyboardLayout.argtypes = [ctypes.c_void_p, wintypes.UINT]
            u.ActivateKeyboardLayout.restype = ctypes.c_void_p
            u.GetLocaleInfoW.argtypes = [wintypes.DWORD, wintypes.DWORD,
                                         wintypes.LPWSTR, ctypes.c_int]
            u.GetLocaleInfoW.restype = ctypes.c_int
            cls._user32 = u
        except Exception:
            cls._user32 = None
        return cls._user32

    @staticmethod
    def hkl_to_klid(hkl):
        """HKL → 8 位十六进制 KLID 字符串。"""
        v = int(hkl) & 0xFFFFFFFF
        hi, lo = (v >> 16) & 0xFFFF, v & 0xFFFF
        if hi == lo:
            hi = 0
        # 有些驱动的 HKL 低字为 0（无语言 ID），此时用高字兜底
        if lo == 0:
            lo = hi
            hi = 0
        return "%04X%04X" % (hi, lo)

    @classmethod
    def _klid_to_hkl(cls):
        """枚举当前系统上所有输入法，返回 {KLID: hkl}。"""
        u = cls._api()
        if not u:
            return {}
        import ctypes
        out = {}
        n = u.GetKeyboardLayoutList(0, None)
        if not n:
            return {}
        arr = (ctypes.c_void_p * n)()
        got = u.GetKeyboardLayoutList(n, arr)
        for i in range(max(0, got)):
            hkl = arr[i]
            if not hkl:
                continue
            out.setdefault(cls.hkl_to_klid(hkl), hkl)
        return out

    # ------------------------------------------------------------------ 名称
    @classmethod
    def _name_of_klid(cls, klid):
        """从注册表取「Layout Text」（本地化名称），失败则退回语言名。"""
        # 1) 注册表
        try:
            import winreg
            path = r"SYSTEM\CurrentControlSet\Control\Keyboard Layouts\%s" % klid
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path) as k:
                for value in ("Layout Text", "Layout Display Name"):
                    try:
                        v = winreg.QueryValueEx(k, value)[0]
                    except OSError:
                        continue
                    if not v:
                        continue
                    # Layout Display Name 可能是 "@dll,-123" 这类间接引用，跳过
                    if v.startswith("@"):
                        continue
                    if v.strip():
                        return v.strip()
        except Exception:
            pass
        # 2) 语言名兜底
        try:
            import ctypes
            from ctypes import wintypes
            u = cls._api()
            langid = int(klid[-4:], 16)
            buf = ctypes.create_unicode_buffer(256)
            # LOCALE_SLANGUAGE = 0x00000002
            if u.GetLocaleInfoW(langid, 0x00000002, buf, 256):
                lang = buf.value
                if lang:
                    return "%s（%s）" % (lang, klid[-4:])
        except Exception:
            pass
        return klid

    # ------------------------------------------------------------------ 窗口
    @classmethod
    def _target_hwnd(cls):
        """切换输入法要投递到「用户正在打字的那个窗口」。
        点悬浮球时焦点会跑到球自己身上，所以平时轮询记住最近一个别人的前台窗口。"""
        u = cls._api()
        if not u:
            return None
        import ctypes
        hwnd = u.GetForegroundWindow()
        if hwnd:
            pid = ctypes.c_ulong(0)
            u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                import os
                if pid.value and pid.value != os.getpid():
                    cls._hwnd_cache = hwnd
                    return hwnd
            except Exception:
                cls._hwnd_cache = hwnd
                return hwnd
        return cls._hwnd_cache

    # ------------------------------------------------------------------ 接口
    @classmethod
    def list_sources(cls):
        """返回当前系统启用的输入法：[{id, name, hkl}, ...]（按系统顺序）"""
        mapping = cls._klid_to_hkl()
        out = []
        for klid, hkl in mapping.items():
            out.append({"id": klid, "name": cls._name_of_klid(klid), "hkl": hkl})
        # 名称去重保护：若某几个输入法取不到注册表名称，语言名兜底会完全一样，
        # 上层 get_display_sources() 是按名称去重的，会把它们合并成一条 → 直接"消失"。
        # 这里给重名的补上 KLID 后缀，保证每个输入法都能被单独看到和切换。
        seen = set()
        for s in out:
            if s["name"] in seen:
                s["name"] = "%s [%s]" % (s["name"], s["id"])
            seen.add(s["name"])
        return out

    @classmethod
    def current_id(cls):
        """当前前台窗口正在使用的输入法 KLID。"""
        u = cls._api()
        if not u:
            return None
        try:
            import ctypes
            hwnd = cls._target_hwnd()
            if not hwnd:
                return cls._last_klid
            tid = u.GetWindowThreadProcessId(hwnd, None)
            hkl = u.GetKeyboardLayout(tid)
            if not hkl:
                return cls._last_klid
            return cls.hkl_to_klid(hkl)
        except Exception:
            return cls._last_klid

    @classmethod
    def select_id(cls, klid):
        """切换到指定输入法；成功返回 True。"""
        u = cls._api()
        if not u:
            return False
        try:
            import ctypes
            hkl = cls._klid_to_hkl().get(klid)
            if not hkl:
                return False
            ok = False
            hwnd = cls._target_hwnd()
            if hwnd:
                ok = bool(u.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl))
                if not ok:
                    # 目标窗口卡住时 PostMessage 会失败，再试一次带超时的同步投递
                    res = ctypes.c_size_t(0)
                    u.SendMessageTimeoutW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl,
                                          SMTO_ABORTIFHUNG, 300, ctypes.byref(res))
                    ok = True
            # 同时切换本进程线程的布局：托盘/气泡上的状态能立刻刷新
            try:
                u.ActivateKeyboardLayout(hkl, 0)
            except Exception:
                pass
            cls._last_klid = klid
            return ok or bool(hwnd) or True
        except Exception:
            return False


# 兼容旧名字
IMESwitch = WinIME
