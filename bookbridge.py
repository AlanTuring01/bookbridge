#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""bookbridge 命令行入口。

子命令：
    render    PDF → 逐页图片
    ocr       对页图做 OCR，生成逐页文本草稿
    draft     OCR 文本 + 繁简转换 → 逐页 Markdown 草稿（机器质量）
    build     逐页 Markdown + book.yaml → EPUB
    verify    校验 EPUB 结构与中文字形
    pipeline  render → ocr → draft 一条龙（随后用 AI 精校，再 build）

典型流程见 README。AI 逐章精校不在本 CLI 内（它需要一个带视觉的 agent），
提示词模板在 prompts/ 下，按章喂给 Claude / 任意多模态 agent 即可。
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from bookbridge import render as R  # noqa: E402
from bookbridge import ocr as O  # noqa: E402
from bookbridge import convert as C  # noqa: E402
from bookbridge import epub as E  # noqa: E402
from bookbridge import verify as V  # noqa: E402


def _load_yaml(path):
    import yaml

    return yaml.safe_load(open(path, encoding="utf-8"))


def cmd_render(a):
    imgs = R.render_pages(a.pdf, a.out, dpi=a.dpi, fmt=a.fmt)
    print(f"渲染 {len(imgs)} 页 → {a.out}")


def cmd_ocr(a):
    imgs = sorted(glob.glob(os.path.join(a.images, "*.png")) + glob.glob(os.path.join(a.images, "*.jpg")))
    if not imgs:
        sys.exit(f"在 {a.images} 找不到页图，请先 render")
    O.run_ocr(imgs, backend=a.backend, langs=a.langs)
    print(f"OCR 完成 {len(imgs)} 页（{a.backend}）")


def cmd_draft(a):
    imgs = sorted(glob.glob(os.path.join(a.images, "*.png")) + glob.glob(os.path.join(a.images, "*.jpg")))
    texts = O.collect_text(imgs, drop_coords=True)
    conv = C.Converter(a.convert, convert_quotes=not a.no_quote_convert) if a.convert != "none" else None
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    blocks = []
    for pno in sorted(texts):
        t = texts[pno]
        if conv and t.strip():
            t = conv(t)
        blocks.append(f"<!-- PAGE {pno} -->\n{t}".rstrip())
    open(a.out, "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
    print(f"逐页 Markdown 草稿 → {a.out}（{len(texts)} 页，转换：{a.convert}）")


def cmd_build(a):
    cfg = _load_yaml(a.config)
    if a.pdf:
        cfg["source_pdf"] = a.pdf
    stats = E.build_epub(cfg, a.pagespec, a.out)
    print("EPUB 已生成：")
    for k, v in stats.items():
        print(f"  {k}: {v}")


def cmd_verify(a):
    errs, warns = V.verify(a.epub, target=a.target)
    print(f"错误 {len(errs)}，警告 {len(warns)}")
    for e in errs:
        print("  [E]", e)
    for w in warns:
        print("  [W]", w)
    sys.exit(1 if errs else 0)


def cmd_pipeline(a):
    print("① 渲染页图…")
    imgs = R.render_pages(a.pdf, a.images, dpi=a.dpi)
    print(f"   {len(imgs)} 页")
    print("② OCR…")
    O.run_ocr(imgs, backend=a.backend, langs=a.langs)
    print("③ 生成逐页草稿…")
    texts = O.collect_text(imgs)
    conv = C.Converter(a.convert) if a.convert != "none" else None
    blocks = []
    for pno in sorted(texts):
        t = texts[pno]
        if conv and t.strip():
            t = conv(t)
        blocks.append(f"<!-- PAGE {pno} -->\n{t}".rstrip())
    open(a.out, "w", encoding="utf-8").write("\n\n".join(blocks) + "\n")
    print(f"   草稿 → {a.out}")
    print("\n机器草稿已就绪。下一步：用 prompts/ 里的模板，按章把页图 + 草稿喂给")
    print("带视觉的 AI 做逐页精校，再 `bookbridge build`。")


def main():
    p = argparse.ArgumentParser(prog="bookbridge", description="把任何 PDF 变成你母语的精校 ePub")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("render", help="PDF → 逐页图片")
    sp.add_argument("pdf")
    sp.add_argument("out", help="输出目录")
    sp.add_argument("--dpi", type=int, default=165)
    sp.add_argument("--fmt", default="png", choices=["png", "jpg"])
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("ocr", help="页图 OCR")
    sp.add_argument("images", help="页图目录")
    sp.add_argument("--backend", default="vision", choices=["vision", "tesseract"])
    sp.add_argument("--langs", default="zh-Hans,zh-Hant,en-US")
    sp.set_defaults(func=cmd_ocr)

    sp = sub.add_parser("draft", help="OCR 文本 + 繁简转换 → 逐页 Markdown")
    sp.add_argument("images", help="页图目录（同名 .txt 为 OCR 结果）")
    sp.add_argument("out", help="输出 .md")
    sp.add_argument("--convert", default="t2s", choices=C.directions() + ["none"])
    sp.add_argument("--no-quote-convert", action="store_true", help="不转换引号风格")
    sp.set_defaults(func=cmd_draft)

    sp = sub.add_parser("build", help="逐页 Markdown + 配置 → EPUB")
    sp.add_argument("config", help="book.yaml")
    sp.add_argument("pagespec", help="逐页 .md 文件或目录")
    sp.add_argument("out", help="输出 .epub")
    sp.add_argument("--pdf", help="覆盖配置里的 source_pdf")
    sp.set_defaults(func=cmd_build)

    sp = sub.add_parser("verify", help="校验 EPUB")
    sp.add_argument("epub")
    sp.add_argument("--target", default="simplified", choices=["simplified", "traditional", "none"])
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("pipeline", help="render→ocr→draft 一条龙")
    sp.add_argument("pdf")
    sp.add_argument("--images", default="pages")
    sp.add_argument("--out", default="draft.md")
    sp.add_argument("--dpi", type=int, default=165)
    sp.add_argument("--backend", default="vision", choices=["vision", "tesseract"])
    sp.add_argument("--langs", default="zh-Hans,zh-Hant,en-US")
    sp.add_argument("--convert", default="t2s", choices=C.directions() + ["none"])
    sp.set_defaults(func=cmd_pipeline)

    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
