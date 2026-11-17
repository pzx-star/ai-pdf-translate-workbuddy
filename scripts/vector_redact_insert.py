# -*- coding: utf-8 -*-
"""PDF 转曲文字矢量翻译：用 redaction 删除转曲字形路径（背景/图片零损伤），
再以原生文字对象插入译文——全程矢量、无任何栅格补丁，不存在色差接缝/淡框。

适用：文字已转曲（页面提取不到文字但有矢量字形路径）的 PDF。
不适用：文字烘焙在位图里的 PDF（那种走 raster_erase_redraw.py）。

用法:
    python vector_redact_insert.py <src.pdf> <out.pdf> --items items.json

items.json 示例（rect 为 PDF 点坐标）:
[
  {"rect": [72.3, 142.1, 119.3, 159.0], "text": "苹果",
   "fontfile": "C:\\Windows\\Fonts\\msyhbd.ttc", "fontsize": 18,
   "color": [0.14, 0.12, 0.13], "max_width": 106},
  {"rect": [197.3, 31.6, 274.0, 48.7], "text": "字母",
   "fontfile": "...", "fontsize": 23, "color": [1, 1, 1], "max_width": 67}
]

- 删除字形：add_redact_annot(rect 外扩 expand pt) + apply_redactions(
  images=PDF_REDACT_IMAGE_NONE,           # 图片绝不触碰
  graphics=PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,  # 只删被完全覆盖的字形路径，大背景/插画保留
  text=PDF_REDACT_TEXT_NONE)
- 插入译文：insert_font 子集嵌入 + insert_text 按实际墨迹中心居中
  （用 PIL getbbox 实测墨迹范围换算基线，CJK/拉丁/西里尔都精确，不依赖字体的 ascender 猜测）。
- CMYK 色彩保真（关键）：原文件为 CMYK 时，items 指定 "cmyk": [C,M,Y,K]——插入后把新内容流里的
  rg/RG 算子改写为对应的 k/K 算子，与原文同一色彩空间、同一条渲染路径，杜绝 RGB/CMYK 双转换色差。
  可选 "gs": "/GS1" 复刻原文的 ExtGState（如 ca=0.9），保证透明混合行为也一致。
- max_width 可选：整词超宽时按比例收缩字号（仅极端长词）。
"""
import argparse
import json
import os
import re

import pymupdf
from PIL import ImageFont

# 原字体无法确定时的默认字体：Arial Rounded MT Bold（用户可用 --font 覆盖）
DEFAULT_FONT = r'C:\Windows\Fonts\ARLRDBD.TTF'


def ink_center_offset(fontfile, text, size):
    """墨迹中心在基线上方多少像素（PIL 实测，y-down 坐标基线在墨迹中心下方）。"""
    f = ImageFont.truetype(fontfile, size)
    bbox = f.getbbox(text)
    ascent, _ = f.getmetrics()
    if bbox is None or bbox[3] <= bbox[1]:
        return 0.0
    return ascent - (bbox[1] + bbox[3]) / 2.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src_pdf')
    ap.add_argument('out_pdf')
    ap.add_argument('--items', required=True)
    ap.add_argument('--expand', type=float, default=1.5,
                    help='redact 矩形外扩(pt)，确保完整覆盖字形笔画')
    ap.add_argument('--font', default=None,
                    help='全局覆盖字体文件路径（用户指定字体优先；未指定且 items 缺 fontfile 时'
                         '用默认 Arial Rounded MT Bold）')
    args = ap.parse_args()

    with open(args.items, encoding='utf-8') as f:
        items = json.load(f)

    for it in items:
        it['fontfile'] = args.font or it.get('fontfile') or DEFAULT_FONT

    doc = pymupdf.open(args.src_pdf)
    page = doc[0]
    contents_before = set(page.get_contents())

    # 1) 删除原字形（一次性应用全部 redaction）
    for it in items:
        x1, y1, x2, y2 = it['rect']
        e = it.get('expand', args.expand)
        page.add_redact_annot(pymupdf.Rect(x1 - e, y1 - e, x2 + e, y2 + e))
    page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                          graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_COVERED,
                          text=pymupdf.PDF_REDACT_TEXT_NONE)

    # 2) 插入译文：每个字体文件注册一次
    aliases = {}
    for it in items:
        ff = it['fontfile']
        if ff not in aliases:
            alias = 'F%d' % len(aliases)
            aliases[ff] = alias
            page.insert_font(fontname=alias, fontfile=ff)
    for it in items:
        text = it['text']
        size = it.get('fontsize', 18)
        color = it.get('color', (0, 0, 0))
        ff = it['fontfile']
        alias = aliases[ff]
        font = pymupdf.Font(fontfile=ff)
        max_w = it.get('max_width')
        if max_w:
            w = font.text_length(text, fontsize=size)
            if w > max_w:
                size = max(6, size * max_w / w)
        w = font.text_length(text, fontsize=size)
        x1, y1, x2, y2 = it['rect']
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        # 基线 = cy + 墨迹中心在基线上方的偏移（PIL 实测，y-down 坐标系）
        off = ink_center_offset(ff, text, size)
        base_y = cy + off
        x = cx - w / 2
        rc = page.insert_text((x, base_y), text, fontname=alias,
                              fontsize=size, color=color)
        if not rc >= 0:
            raise SystemExit('insert_text failed: %r (rc=%r)' % (text, rc))
        print('insert %r size=%.2f w=%.1f at (%.1f, %.1f) color=%s' % (
            text, size, w, x, base_y, tuple(round(c, 2) for c in color)))

    # 3) CMYK 保真：把插入内容流里的 rg/RG 改写为原文同款 k/K 算子，并复刻 ExtGState
    cmyk_items = [it for it in items if it.get('cmyk')]
    if cmyk_items:
        # RGB -> CMYK 字符串映射（tolerance 匹配）
        def rgb_key(c):
            return tuple(round(v, 3) for v in c)
        mapping = {rgb_key(it.get('color', (0, 0, 0))):
                   ' '.join('%.4g' % v for v in it['cmyk']) for it in cmyk_items}

        def make_repl(suffix):
            def repl(m):
                rgb = tuple(float(v) for v in m.groups())
                for key, cmyk_str in mapping.items():
                    if all(abs(a - b) < 0.02 for a, b in zip(rgb, key)):
                        return '%s %s' % (cmyk_str, suffix)
                return m.group(0)
            return repl

        gs = cmyk_items[0].get('gs')
        for xref in page.get_contents():
            if xref in contents_before:
                continue
            s = doc.xref_stream(xref).decode('latin-1')
            s = re.sub(r'([\d.]+) ([\d.]+) ([\d.]+) rg', make_repl('k'), s)
            s = re.sub(r'([\d.]+) ([\d.]+) ([\d.]+) RG', make_repl('K'), s)
            if gs and 'BT' in s and s.lstrip().startswith('q'):
                s = s.replace('q\n', 'q\n%s gs\n' % gs, 1)
            doc.update_stream(xref, s.encode('latin-1'))
        print('CMYK rewrite: %d 处算子, gs=%s' % (len(cmyk_items), gs or '无'))

    doc.save(args.out_pdf, garbage=3, deflate=True)
    print('saved', args.out_pdf, '(矢量路线, 原图片/背景零改动)')


if __name__ == '__main__':
    main()
