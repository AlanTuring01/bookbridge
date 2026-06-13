# -*- coding: utf-8 -*-
"""OCR 编排层。

默认后端是 macOS 的 Vision 框架（CJK 识别质量好、本地、免费）；
若不在 macOS，可改用 Tesseract（需自行安装 `tesseract` 与对应语言包）。

每页 OCR 结果先写成「带坐标前缀」的 .txt，再由 strip_coords() 去掉坐标
得到纯文本草稿。坐标信息保留在 .txt 里，方便需要时按版面重排。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

_COORD = re.compile(r"^\[[\d.,]+\]\s?(.*)$")
_HERE = os.path.dirname(os.path.abspath(__file__))
_SWIFT_SRC = os.path.join(_HERE, "vision_ocr.swift")
_SWIFT_BIN = os.path.join(_HERE, "vision_ocr")


def strip_coords(text: str) -> str:
    """去掉每行的 [x,y,w,h] 坐标前缀，只留文本。"""
    out = []
    for ln in text.splitlines():
        m = _COORD.match(ln)
        out.append(m.group(1) if m else ln)
    return "\n".join(out)


# ---------- macOS Vision ----------

def _ensure_vision_built() -> str:
    if sys.platform != "darwin":
        raise RuntimeError("Vision 后端仅支持 macOS；非 macOS 请用 backend='tesseract'")
    need = (not os.path.exists(_SWIFT_BIN)) or (
        os.path.getmtime(_SWIFT_SRC) > os.path.getmtime(_SWIFT_BIN)
    )
    if need:
        subprocess.run(
            ["swiftc", "-O", _SWIFT_SRC, "-o", _SWIFT_BIN],
            check=True,
        )
    return _SWIFT_BIN


def ocr_vision(images: list[str], langs: str = "zh-Hans,zh-Hant,en-US") -> None:
    """对一批图片运行 Vision OCR，就地生成同名 .txt。"""
    binary = _ensure_vision_built()
    # 分批，避免命令行过长
    batch = 50
    for i in range(0, len(images), batch):
        chunk = images[i : i + batch]
        subprocess.run([binary, "--langs", langs, *chunk], check=True,
                       stdout=subprocess.DEVNULL)


# ---------- Tesseract（跨平台后备） ----------

def ocr_tesseract(images: list[str], lang: str = "chi_sim+chi_tra+eng") -> None:
    for img in images:
        out = os.path.splitext(img)[0]
        subprocess.run(
            ["tesseract", img, out, "-l", lang],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )


# ---------- 统一入口 ----------

def run_ocr(
    images: list[str],
    backend: str = "vision",
    langs: str = "zh-Hans,zh-Hant,en-US",
) -> None:
    if backend == "vision":
        ocr_vision(images, langs=langs)
    elif backend == "tesseract":
        ocr_tesseract(images)
    else:
        raise ValueError(f"未知 OCR 后端：{backend}")


def collect_text(images: list[str], drop_coords: bool = True) -> dict[int, str]:
    """读取与图片同名的 .txt，返回 {页码: 文本}。页码从文件名 pNNN 推断。"""
    result: dict[int, str] = {}
    for img in images:
        stem = os.path.splitext(img)[0]
        txt_path = stem + ".txt"
        m = re.search(r"(\d+)$", os.path.basename(stem))
        pno = int(m.group(1)) if m else len(result) + 1
        text = ""
        if os.path.exists(txt_path):
            text = open(txt_path, encoding="utf-8").read()
            if drop_coords:
                text = strip_coords(text)
        result[pno] = text
    return result
