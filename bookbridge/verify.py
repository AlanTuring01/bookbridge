# -*- coding: utf-8 -*-
"""EPUB 结构与中文质量校验。

检查：打包规范（mimetype 首条目且不压缩）、容器/OPF、XML 良构、
manifest/spine 与内部链接完整、文档非空、无残留处理标记，
以及（针对中文）目标字形是否纯净（不该出现的繁体/简体字、引号风格）。
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
import zipfile

# 这些高频繁体字若出现在「简体目标」里，多半是漏转（「著」合法故不列）
_TRAD_SAMPLE = "裏裡後門開關說學國經會時長東車書語頭點臺眾廣題雙這樣們嗎為麼從億價發見聞讀寫變應對義務權"


def verify(path: str, target: str = "simplified") -> tuple[list[str], list[str]]:
    """返回 (errors, warnings)。target: simplified / traditional / none。"""
    errors: list[str] = []
    warns: list[str] = []
    z = zipfile.ZipFile(path)
    names = z.namelist()

    info0 = z.infolist()[0]
    if info0.filename != "mimetype":
        errors.append("mimetype 不是首个条目")
    elif info0.compress_type != zipfile.ZIP_STORED:
        errors.append("mimetype 被压缩（必须 STORED）")
    elif z.read("mimetype") != b"application/epub+zip":
        errors.append("mimetype 内容错误")

    ct = z.read("META-INF/container.xml").decode()
    m = re.search(r'full-path="([^"]+)"', ct)
    if not m:
        errors.append("container.xml 缺 full-path")
        return errors, warns
    opf_path = m.group(1)
    if opf_path not in names:
        errors.append(f"OPF 缺失: {opf_path}")
        return errors, warns
    opf = z.read(opf_path).decode()
    root = opf_path.rsplit("/", 1)[0] + "/" if "/" in opf_path else ""

    for n in [x for x in names if x.endswith((".xhtml", ".opf", ".xml"))]:
        try:
            ET.fromstring(z.read(n))
        except ET.ParseError as e:
            errors.append(f"XML 解析失败 {n}: {e}")

    hrefs = re.findall(r'<item [^>]*href="([^"]+)"', opf)
    ids = dict(re.findall(r'<item id="([^"]+)" href="([^"]+)"', opf))
    for h in hrefs:
        if root + h not in names:
            errors.append(f"manifest 引用缺失: {h}")
    for idref in re.findall(r'<itemref idref="([^"]+)"', opf):
        if idref not in ids:
            errors.append(f"spine 未知 id: {idref}")

    for n in [x for x in names if x.endswith(".xhtml")]:
        base = n.rsplit("/", 1)[0]
        content = z.read(n).decode()
        for mm in re.finditer(r'(?:src|href)="([^"#]+)"', content):
            ref = mm.group(1)
            if ref.startswith(("http:", "https:", "mailto:")):
                continue
            parts, out = (base + "/" + ref).split("/"), []
            for p in parts:
                if p == "..":
                    out and out.pop()
                elif p != ".":
                    out.append(p)
            if "/".join(out) not in names:
                errors.append(f"{n} 链接缺失: {ref}")

    for n in [x for x in names if x.endswith(".xhtml")]:
        c = z.read(n).decode()
        if re.search(r"<!--\s*(PAGE|CONT|FIGURE|DESIGN-PAGE|BLANK)", c):
            warns.append(f"{n} 残留处理标记")
        bm = re.search(r"<body>(.*)</body>", c, re.S)
        body = bm.group(1).strip() if bm else ""
        if len(body) < 40 and not any(k in n for k in ("part", "cover")):
            warns.append(f"{n} 内容近乎为空 ({len(body)}B)")
        # 中文字形/引号
        if target == "simplified":
            trad = [ch for ch in _TRAD_SAMPLE if ch in body]
            if trad:
                warns.append(f"{n} 疑似繁体残留: {''.join(trad)}")
            if "「" in body or "『" in body:
                errors.append(f"{n} 残留直角引号「」/『』（简体应用“”）")
            if "甚么" in body:
                errors.append(f"{n} 「甚么」未转「什么」")
        elif target == "traditional":
            if "“" in body or "‘" in body:
                warns.append(f"{n} 出现弯引号（繁体习惯用「」）")

    return errors, warns


def main(argv=None):
    argv = argv or sys.argv[1:]
    if not argv:
        print("usage: python -m bookbridge.verify <epub> [simplified|traditional|none]")
        return 2
    path = argv[0]
    target = argv[1] if len(argv) > 1 else "simplified"
    errors, warns = verify(path, target)
    z = zipfile.ZipFile(path)
    print(f"文件数: {len(z.namelist())}")
    print(f"错误: {len(errors)}")
    for e in errors[:40]:
        print("  [E]", e)
    print(f"警告: {len(warns)}")
    for w in warns[:40]:
        print("  [W]", w)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
