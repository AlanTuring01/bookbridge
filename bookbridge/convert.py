# -*- coding: utf-8 -*-
"""中文繁简互转，基于 OpenCC。

支持方向：
    t2s    繁体 → 简体（默认，本仓库初次实践方向）
    s2t    简体 → 繁体
    s2tw   简体 → 繁体（台湾正体）
    tw2s   繁体（台湾正体）→ 简体
    s2twp  简体 → 繁体（台湾正体，含常用词转换，如「软件」→「軟體」）
    tw2sp  繁体（台湾正体）→ 简体（含常用词转换）
    s2hk   简体 → 繁体（香港）
    hk2s   繁体（香港）→ 简体

引号风格转换是可选的、独立于字形转换的一步：
    简体习惯用弯引号 “ ” ‘ ’
    繁体（港台）习惯用直角引号 「 」 『 』
"""
from __future__ import annotations

# 字形转换方向 → OpenCC 配置名
_CONFIGS = {
    "t2s": "t2s",
    "s2t": "s2t",
    "s2tw": "s2tw",
    "tw2s": "tw2s",
    "s2twp": "s2twp",
    "tw2sp": "tw2sp",
    "s2hk": "s2hk",
    "hk2s": "hk2s",
}

# 转换后目标是简体还是繁体（决定引号风格）
_TARGET_IS_SIMPLIFIED = {
    "t2s": True, "tw2s": True, "tw2sp": True, "hk2s": True,
    "s2t": False, "s2tw": False, "s2twp": False, "s2hk": False,
}

_QUOTES_TO_CURLY = str.maketrans({"「": "“", "」": "”", "『": "‘", "』": "’"})
_QUOTES_TO_CORNER = str.maketrans({"“": "「", "”": "」", "‘": "『", "’": "』"})

# OpenCC 字形转换后，简体目标仍有少量「词形」遗留需要规范化。
# 这里只放绝对安全、无歧义的整词替换（如「甚麼/甚么」恒等于「什么」）。
_SIMP_WORD_FIXES = {
    "甚麼": "什么",
    "甚么": "什么",
}


class Converter:
    """惰性加载 OpenCC，可重复调用。"""

    def __init__(self, direction: str = "t2s", convert_quotes: bool = True):
        if direction not in _CONFIGS:
            raise ValueError(
                f"未知方向 {direction!r}，可选：{', '.join(_CONFIGS)}"
            )
        self.direction = direction
        self.convert_quotes = convert_quotes
        self._cc = None

    def _engine(self):
        if self._cc is None:
            from opencc import OpenCC

            self._cc = OpenCC(_CONFIGS[self.direction])
        return self._cc

    def __call__(self, text: str) -> str:
        out = self._engine().convert(text)
        if _TARGET_IS_SIMPLIFIED[self.direction]:
            for a, b in _SIMP_WORD_FIXES.items():
                out = out.replace(a, b)
        if self.convert_quotes:
            if _TARGET_IS_SIMPLIFIED[self.direction]:
                out = out.translate(_QUOTES_TO_CURLY)
            else:
                out = out.translate(_QUOTES_TO_CORNER)
        return out


def convert(text: str, direction: str = "t2s", convert_quotes: bool = True) -> str:
    """一次性转换的便捷函数。"""
    return Converter(direction, convert_quotes)(text)


def directions() -> list[str]:
    return list(_CONFIGS)
