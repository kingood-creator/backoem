#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""macOS 输入法后端（Carbon / TIS，纯 ctypes，无第三方依赖）。

对外只暴露一个类：MacIME，接口与 Windows 后端的 WinIME 完全一致——
    list_sources() -> [{"id", "name", "ref"}, ...]
    current_id()   -> str | None
    select_id(sid) -> bool

这样 ime_float.py 里的 GUI 代码不需要知道自己在哪个平台上跑。
"""

import ctypes
import ctypes.util
from ctypes import cdll, c_void_p, c_int, c_bool, c_char_p, create_string_buffer


class MacIME:
    """封装 macOS Text Input Source 切换接口。"""

    _carbon = None
    _keys = {}
    _last_array = None  # 保持引用，防止元素指针失效

    @classmethod
    def _load(cls):
        if cls._carbon is not None:
            return
        carbon = cdll.LoadLibrary(ctypes.util.find_library("Carbon"))
        # 使用「导出常量」作为属性键（用 CFStringCreateWithCString 自建的常量
        # 在部分属性上 CFEqual 不成立，会被 TIS 拒绝），只读取确实导出的键。
        k = {}
        for name in ("kTISPropertyInputSourceID",
                     "kTISPropertyLocalizedName",
                     "kTISPropertyInputModeID"):
            try:
                k[name[1:]] = c_void_p.in_dll(carbon, name)
            except Exception:
                pass
        carbon.TISCreateInputSourceList.argtypes = [c_void_p, c_bool]
        carbon.TISCreateInputSourceList.restype = c_void_p
        carbon.CFArrayGetCount.argtypes = [c_void_p]
        carbon.CFArrayGetCount.restype = c_int
        carbon.CFArrayGetValueAtIndex.argtypes = [c_void_p, c_int]
        carbon.CFArrayGetValueAtIndex.restype = c_void_p
        carbon.TISGetInputSourceProperty.argtypes = [c_void_p, c_void_p]
        carbon.TISGetInputSourceProperty.restype = c_void_p
        carbon.TISCopyCurrentKeyboardInputSource.restype = c_void_p
        carbon.TISCopyCurrentKeyboardInputSource.argtypes = []
        carbon.TISSelectInputSource.argtypes = [c_void_p]
        carbon.TISSelectInputSource.restype = c_int
        carbon.CFStringGetLength.restype = c_int
        carbon.CFStringGetLength.argtypes = [c_void_p]
        carbon.CFStringGetCString.argtypes = [c_void_p, c_char_p, c_int, c_int]
        carbon.CFStringGetCString.restype = c_bool
        cls._carbon = carbon
        cls._keys = k

    @classmethod
    def _cfstr_to_py(cls, cf):
        if not cf:
            return None
        c = cls._carbon
        L = c.CFStringGetLength(cf)
        buf = create_string_buffer((L + 1) * 4)
        if c.CFStringGetCString(cf, buf, len(buf), 0x08000100):
            return buf.value.decode("utf-8")
        return None

    @classmethod
    def list_sources(cls):
        """返回所有键盘输入源列表：[ {id, name, ref}, ... ]"""
        cls._load()
        c = cls._carbon
        arr = c.TISCreateInputSourceList(None, False)
        cls._last_array = arr  # 保持存活
        n = c.CFArrayGetCount(arr)
        out = []
        for i in range(n):
            src = c.CFArrayGetValueAtIndex(arr, i)
            sid = cls._cfstr_to_py(c.TISGetInputSourceProperty(src, cls._keys.get("TISPropertyInputSourceID")))
            if not sid:
                continue
            nm = cls._cfstr_to_py(c.TISGetInputSourceProperty(src, cls._keys.get("TISPropertyLocalizedName")))
            out.append({"id": sid, "name": nm or sid, "ref": src})
        return out

    @classmethod
    def current_id(cls):
        cls._load()
        c = cls._carbon
        cur = c.TISCopyCurrentKeyboardInputSource()
        return cls._cfstr_to_py(c.TISGetInputSourceProperty(cur, cls._keys.get("TISPropertyInputSourceID")))

    @classmethod
    def select_id(cls, sid):
        """按输入源 ID 切换；成功返回 True。"""
        cls._load()
        for s in cls.list_sources():
            if s["id"] == sid:
                return cls._carbon.TISSelectInputSource(s["ref"]) == 0
        return False


# 兼容旧名字
IMESwitch = MacIME
