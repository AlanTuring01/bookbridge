# -*- coding: utf-8 -*-
"""把 PDF 每一页渲染成图片，供 OCR 与 ePub 嵌图使用。"""
from __future__ import annotations

import os
from typing import Iterable, Optional


def render_pages(
    pdf_path: str,
    out_dir: str,
    dpi: int = 165,
    fmt: str = "png",
    pages: Optional[Iterable[int]] = None,
    prefix: str = "p",
) -> list[str]:
    """渲染 PDF 页面为图片。

    参数
        pdf_path  源 PDF 路径
        out_dir   输出目录（不存在则创建）
        dpi       渲染分辨率，OCR 建议 150–200，嵌图 130–165 足够
        fmt       png / jpg
        pages     要渲染的页码（1 起，None 表示全部）
        prefix    文件名前缀，输出形如 p001.png

    返回 生成的图片路径列表（按页序）。
    """
    import fitz  # PyMuPDF

    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    total = doc.page_count
    want = list(pages) if pages is not None else range(1, total + 1)

    written: list[str] = []
    for pno in want:
        if pno < 1 or pno > total:
            continue
        page = doc[pno - 1]
        pix = page.get_pixmap(dpi=dpi)
        name = f"{prefix}{pno:03d}.{fmt}"
        path = os.path.join(out_dir, name)
        if fmt.lower() in ("jpg", "jpeg"):
            try:
                data = pix.tobytes("jpeg", jpg_quality=85)
            except Exception:
                data = pix.tobytes("jpeg")
            with open(path, "wb") as f:
                f.write(data)
        else:
            pix.save(path)
        written.append(path)
    doc.close()
    return written


def page_count(pdf_path: str) -> int:
    import fitz

    doc = fitz.open(pdf_path)
    n = doc.page_count
    doc.close()
    return n


def get_toc(pdf_path: str) -> list[tuple[int, str, int]]:
    """读取 PDF 自带书签目录：[(层级, 标题, 页码), ...]。"""
    import fitz

    doc = fitz.open(pdf_path)
    toc = doc.get_toc()
    doc.close()
    return toc


def has_text_layer(pdf_path: str, sample: int = 8) -> bool:
    """抽样判断 PDF 是否已有文本层（有则无需 OCR）。"""
    import fitz

    doc = fitz.open(pdf_path)
    n = doc.page_count
    step = max(1, n // sample)
    chars = 0
    for i in range(0, n, step):
        chars += len(doc[i].get_text().strip())
    doc.close()
    return chars > 40 * sample
