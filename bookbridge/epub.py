# -*- coding: utf-8 -*-
"""把「逐页 Markdown」组装成 EPUB 3。

逐页 Markdown 用一组注释标记承载版面信息：

    <!-- PAGE 21 -->            一页的开始（页码用源 PDF 的页序）
    <!-- CONT -->               本页开头是上一页段落的接续
    <!-- BLANK page=2 -->        空白页
    <!-- DESIGN-PAGE page=21 title="第一章 ..." -->
                                整页设计页（扉页等），以原页图呈现
    <!-- FIGURE page=79 type=图表 caption="..." -->
                                此处有照片/图表/信息图，按需嵌入原页图

书的元数据与章节结构由 book.yaml 提供，见 examples/book.example.yaml。
"""
from __future__ import annotations

import html
import os
import re
import uuid
import zipfile
from typing import Optional

import markdown

# 哪些图类型值得整页嵌入（纯装饰小插画不嵌）
EMBED_TYPES = {"照片", "图表", "信息图", "二维码", "photo", "chart", "figure", "infographic"}

CSS = """
body { font-family: "Songti SC", "Noto Serif CJK SC", "Noto Serif CJK TC", serif; line-height: 1.75; margin: 0 5%; }
h1 { font-size: 1.5em; text-align: center; margin: 2em 0 1.5em; font-weight: bold; }
h2 { font-size: 1.2em; margin: 1.8em 0 0.8em; font-weight: bold; }
h3 { font-size: 1.05em; margin: 1.5em 0 0.6em; font-weight: bold; }
p { text-indent: 2em; margin: 0 0 0.4em; text-align: justify; }
.design-page { text-align: center; margin: 0; }
.design-page img { max-width: 100%; max-height: 95vh; }
figure.page-figure { text-align: center; margin: 1.5em 0; page-break-inside: avoid; }
figure.page-figure img { max-width: 100%; }
figcaption { font-size: 0.85em; color: #555; margin-top: 0.4em; text-indent: 0; }
table { border-collapse: collapse; margin: 1em auto; font-size: 0.9em; }
th, td { border: 1px solid #888; padding: 0.3em 0.6em; }
blockquote { margin: 1em 2em; color: #333; }
.cover { text-align: center; margin: 0; }
.cover img { max-width: 100%; max-height: 98vh; }
.missing { color: #a00; text-align: center; }
"""

_XHTML = """<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">
<head><title>{title}</title><link rel="stylesheet" type="text/css" href="../css/style.css"/></head>
<body>
{body}
</body>
</html>"""


# ---------------- 解析逐页 Markdown ----------------

def load_pages(pagespec: str) -> tuple[dict[int, str], dict[int, dict]]:
    """读入一个 .md 文件或一个目录里的所有 .md，返回 (pages, flags)。"""
    texts = []
    if os.path.isdir(pagespec):
        for name in sorted(os.listdir(pagespec)):
            if name.endswith(".md"):
                texts.append(open(os.path.join(pagespec, name), encoding="utf-8").read())
    else:
        texts.append(open(pagespec, encoding="utf-8").read())

    pages: dict[int, str] = {}
    flags: dict[int, dict] = {}
    for text in texts:
        parts = re.split(r"<!--\s*PAGE\s+(\d+)\s*-->", text)
        for i in range(1, len(parts) - 1, 2):
            pno = int(parts[i])
            body = parts[i + 1].strip("\n")
            pages[pno] = body
            fl = {"design": None, "blank": False, "figures": []}
            m = re.search(rf'<!--\s*DESIGN-PAGE\s+page={pno}(?:\s+title="([^"]*)")?\s*-->', body)
            if m:
                fl["design"] = m.group(1) or ""
            if re.search(rf"<!--\s*BLANK\s+page={pno}\s*-->", body):
                fl["blank"] = True
            for fm in re.finditer(
                rf'<!--\s*FIGURE\s+page={pno}\s+type=(\S+)(?:\s+caption="([^"]*)")?\s*-->', body
            ):
                fl["figures"].append({"type": fm.group(1), "caption": fm.group(2) or ""})
            flags[pno] = fl
        # 兼容只写了 BLANK/DESIGN-PAGE 而没有 PAGE 包裹的情况
        for m in re.finditer(
            r'<!--\s*(BLANK|DESIGN-PAGE)\s+page=(\d+)(?:\s+title="([^"]*)")?\s*-->', text
        ):
            pno = int(m.group(2))
            if pno not in pages:
                pages[pno] = m.group(0)
                flags[pno] = {
                    "design": (m.group(3) or "") if m.group(1) == "DESIGN-PAGE" else None,
                    "blank": m.group(1) == "BLANK",
                    "figures": [],
                }
    return pages, flags


# ---------------- 抽文引语去重（页眉重复正文的设计性摘句） ----------------

def _norm(s: str) -> str:
    return re.sub(r"[\s>*＊，。、；：“”‘’「」『』！？…·\-—\(\)（）.,;:!?\"']+", "", s)


def dedupe_pullquotes(pages: dict[int, str]) -> int:
    all_norm = _norm("\n".join(pages.values()))
    removed = 0
    for pno, body in list(pages.items()):
        lines = body.split("\n")
        out, i, changed = [], 0, False
        while i < len(lines):
            ln = lines[i]
            if ln.startswith("> ") and all(
                (l.startswith("> ") or not l.strip() or l.startswith("<!--")) for l in lines[:i]
            ):
                j, quote = i, []
                while j < len(lines) and (lines[j].startswith(">") or not lines[j].strip()):
                    if lines[j].startswith(">"):
                        quote.append(lines[j].lstrip("> "))
                    j += 1
                qn = _norm("".join(quote))
                rest = _norm(body.replace("\n".join(lines[i:j]), ""))
                if qn and (qn in all_norm.replace(qn, "", 1) or qn in rest):
                    i, changed = j, True
                    removed += 1
                    continue
            out.append(ln)
            i += 1
        if changed:
            pages[pno] = "\n".join(out)
    return removed


# ---------------- 渲染单页为 XHTML 片段 ----------------

class _Builder:
    def __init__(self, pdf_path, pages, flags, img_dir, lang):
        import fitz

        self.doc = fitz.open(pdf_path)
        self.pages = pages
        self.flags = flags
        self.img_dir = img_dir
        self.lang = lang
        self.md = markdown.Markdown(extensions=["tables"])
        os.makedirs(img_dir, exist_ok=True)

    def render_jpg(self, pno, dpi=150, quality=85):
        path = os.path.join(self.img_dir, f"page{pno:03d}.jpg")
        if not os.path.exists(path):
            pix = self.doc[pno - 1].get_pixmap(dpi=dpi)
            try:
                data = pix.tobytes("jpeg", jpg_quality=quality)
            except Exception:
                data = pix.tobytes("jpeg")
            open(path, "wb").write(data)
        return f"page{pno:03d}.jpg"

    def is_plain(self, pno, thresh=8.0):
        import fitz

        pix = self.doc[pno - 1].get_pixmap(dpi=30, colorspace=fitz.csGRAY)
        vals = list(pix.samples)
        if not vals:
            return True
        mean = sum(vals) / len(vals)
        var = sum((v - mean) ** 2 for v in vals) / len(vals)
        return var ** 0.5 < thresh

    def page_html(self, pno):
        body = self.pages.get(pno)
        if body is None:
            return f'<p class="missing">〔缺：原书第 {pno} 页〕</p>'
        fl = self.flags[pno]
        if fl["blank"]:
            return ""
        if fl["design"] is not None:
            rest = re.sub(r"<!--\s*DESIGN-PAGE[^>]*-->", "", body).strip()
            if not fl["design"] and not rest and self.is_plain(pno):
                return ""
            img = self.render_jpg(pno)
            rest = re.sub(r"<!--\s*(FIGURE|BLANK|DESIGN-PAGE|CONT)[^>]*-->", "", rest).strip()
            self.md.reset()
            rest_html = self.md.convert(rest) if rest else ""
            return (
                f'<div class="design-page"><img src="../images/{img}" '
                f'alt="{html.escape(fl["design"])}"/></div>\n' + rest_html
            )
        has_fig = any(f["type"] in EMBED_TYPES for f in fl["figures"])
        captions = [f["caption"] for f in fl["figures"] if f["caption"]]
        body = re.sub(r"<!--\s*(FIGURE|BLANK|DESIGN-PAGE)[^>]*-->", "", body)
        body = re.sub(r"<!--\s*CONT\s*-->", "<!--CONT-->", body)
        cont = body.lstrip().startswith("<!--CONT-->")
        body = body.replace("<!--CONT-->", "")
        self.md.reset()
        h = self.md.convert(body.strip())
        if cont:
            h = re.sub(r"^<p>", '<p class="cont">', h, count=1)
        if has_fig:
            img = self.render_jpg(pno)
            cap = "；".join(captions)
            cap_html = f"<figcaption>{html.escape(cap)}</figcaption>" if cap else ""
            h += (
                f'\n<figure class="page-figure"><img src="../images/{img}" '
                f'alt="原书第 {pno} 页版面"/>{cap_html}</figure>'
            )
        return h

    def section_html(self, start, end):
        chunks = [self.page_html(p) for p in range(start, end + 1)]
        out = "\n".join(c for c in chunks if c)
        # 合并跨页接续段落
        prev = None
        while prev != out:
            prev = out
            out = re.sub(r'([^>])</p>\s*<p class="cont">', lambda m: m.group(1), out)
        out = out.replace('<p class="cont">', "<p>")
        return out


# ---------------- 目录导航 ----------------

def _build_nav(items):
    out, idx = [], 0

    def rec(level):
        nonlocal idx
        out.append("<ol>")
        while idx < len(items):
            lvl, a = items[idx]
            if lvl < level:
                break
            if lvl == level:
                idx += 1
                nxt = items[idx][0] if idx < len(items) else 0
                if nxt > level:
                    out.append(f"<li>{a}")
                    rec(level + 1)
                    out.append("</li>")
                else:
                    out.append(f"<li>{a}</li>")
            else:
                rec(level + 1)
        out.append("</ol>")

    rec(1)
    return "\n".join(out)


# ---------------- 主入口 ----------------

def build_epub(config: dict, pagespec: str, out_path: str, work_img_dir: Optional[str] = None) -> dict:
    """根据 config 与逐页 Markdown 组装 EPUB，写入 out_path。返回统计信息。"""
    meta = config["metadata"]
    lang = meta.get("language", "zh-CN")
    pdf_path = config["source_pdf"]
    structure = config["structure"]
    cover_page = config.get("cover_page")

    img_dir = work_img_dir or os.path.join(os.path.dirname(out_path) or ".", "_bb_images")
    pages, flags = load_pages(pagespec)
    removed = dedupe_pullquotes(pages)
    b = _Builder(pdf_path, pages, flags, img_dir, lang)

    docs, manifest, spine, nav_items = {}, [], [], []

    # 封面（可选）
    if cover_page:
        cover_img = b.render_jpg(cover_page, dpi=180, quality=88)
        docs["cover"] = _XHTML.format(
            lang=lang, title="封面",
            body=f'<div class="cover"><img src="../images/{cover_img}" alt="cover"/></div>',
        )
        manifest.append(("cover", "text/cover.xhtml"))
        spine.append("cover")
    else:
        cover_img = None

    for sec in structure:
        sid = sec["id"]
        s, e = sec["pages"]
        body = b.section_html(s, e)
        if sec.get("backmatter_figure_first"):
            m = re.search(r'<figure class="page-figure">.*?</figure>', body, re.S)
            if m:
                body = m.group(0) + "\n" + body.replace(m.group(0), "")
        title = sec.get("title") or meta.get("title", "")
        docs[sid] = _XHTML.format(lang=lang, title=html.escape(title), body=body)
        manifest.append((sid, f"text/{sid}.xhtml"))
        spine.append(sid)
        if sec.get("toc") and sec.get("level", 0):
            nav_items.append((sec["level"], f'<a href="text/{sid}.xhtml">{html.escape(sec["toc"])}</a>'))

    nav_html = (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="{lang}" lang="{lang}">\n'
        '<head><title>目录</title><link rel="stylesheet" type="text/css" href="css/style.css"/></head>\n'
        '<body><nav epub:type="toc" id="toc"><h1>目录</h1>\n'
        f"{_build_nav(nav_items)}\n</nav></body></html>"
    )

    imgs = sorted(set(os.listdir(img_dir)))
    book_id = "urn:uuid:" + str(uuid.uuid5(uuid.NAMESPACE_URL, meta.get("title", "bookbridge")))
    img_manifest = "\n".join(
        f'    <item id="img{i}" href="images/{n}" media-type="image/jpeg"'
        + (' properties="cover-image"' if n == cover_img else "")
        + "/>"
        for i, n in enumerate(imgs)
    )
    doc_manifest = "\n".join(f'    <item id="{i}" href="{h}" media-type="application/xhtml+xml"/>' for i, h in manifest)
    spine_xml = "\n".join(f'    <itemref idref="{s}"/>' for s in spine)
    creators = "\n".join(f"    <dc:creator>{html.escape(a)}</dc:creator>" for a in meta.get("authors", []))
    modified = meta.get("modified", "2026-01-01T00:00:00Z")

    opf = f"""<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="bookid" xml:lang="{lang}">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="bookid">{book_id}</dc:identifier>
    <dc:title>{html.escape(meta.get("title", ""))}</dc:title>
{creators}
    <dc:language>{lang}</dc:language>
    <dc:publisher>{html.escape(meta.get("publisher", ""))}</dc:publisher>
    <dc:description>{html.escape(meta.get("description", ""))}</dc:description>
    <meta property="dcterms:modified">{modified}</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="css" href="css/style.css" media-type="text/css"/>
{doc_manifest}
{img_manifest}
  </manifest>
  <spine>
{spine_xml}
  </spine>
</package>"""

    container = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
        '  <rootfiles><rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/></rootfiles>\n'
        "</container>"
    )

    if os.path.exists(out_path):
        os.remove(out_path)
    z = zipfile.ZipFile(out_path, "w")
    z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
    z.writestr("META-INF/container.xml", container)
    z.writestr("OEBPS/content.opf", opf)
    z.writestr("OEBPS/nav.xhtml", nav_html)
    z.writestr("OEBPS/css/style.css", CSS)
    for sid, h in docs.items():
        z.writestr(f"OEBPS/text/{sid}.xhtml", h)
    for n in imgs:
        z.write(os.path.join(img_dir, n), f"OEBPS/images/{n}")
    z.close()

    return {
        "out": out_path,
        "size_mb": round(os.path.getsize(out_path) / 1048576, 1),
        "pages": len(pages),
        "images": len(imgs),
        "sections": len(structure),
        "toc_entries": len(nav_items),
        "pullquotes_removed": removed,
    }
