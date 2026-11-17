# -*- coding: utf-8 -*-
"""矢量文本替换：对未转曲的 .ai / PDF 直接替换文本对象，保留字号/颜色/居中位置，输出仍是活的矢量文本。

用法:
    python translate_vector.py <src> <out_pdf> --map mapping.json [--font C:\\Windows\\Fonts\\xx.ttf] [--png 3]

mapping.json: {"apple": "pomme", "Letters": "Lettres", ...}  （按 span 全文 strip 后精确匹配）

原理: 对每个命中的 span 加 redact annot 只删文字（不动图片和线稿），再用 TextWriter 以
原基线 origin[1]、原字号写新词，按原 bbox 中心水平居中，颜色沿用原 span（白/深色分别写入）。
"""
import argparse
import json
import os

import pymupdf

DARK_DEFAULT = (0x23 / 255, 0x19 / 255, 0x16 / 255)


def pick_font(font_path, all_new_text):
    """加载字体并校验所有目标字符都有字形（œ é à ç 等特殊字符最常缺）。"""
    if font_path and os.path.isfile(font_path):
        font = pymupdf.Font(fontfile=font_path)
    else:
        raise SystemExit('必须用 --font 指定一个覆盖目标语言的 TTF/OTF 字体')
    missing = sorted({c for w in all_new_text for c in w if not font.has_glyph(ord(c))})
    if missing:
        raise SystemExit('字体 %s 缺字形: %s -> 换一个字体（如 msyhbd.ttc / 思源黑体）' % (font_path, ' '.join(missing)))
    return font


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('out')
    ap.add_argument('--map', required=True, help='mapping.json 路径')
    ap.add_argument('--font', default='', help='目标语言字体文件路径')
    ap.add_argument('--png', type=int, default=0, help='渲染倍率预览，0=不渲染')
    args = ap.parse_args()

    with open(args.map, encoding='utf-8') as f:
        mapping = json.load(f)

    doc = pymupdf.open(args.src)
    font = pick_font(args.font, set(mapping.values()))
    print('font:', font.name)

    total = 0
    for pno, page in enumerate(doc):
        targets = []
        for b in page.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                for s in line['spans']:
                    if s['text'].strip() in mapping:
                        targets.append(s)
        if not targets:
            continue

        # 只删文字：图片与线稿一律保留
        for s in targets:
            page.add_redact_annot(pymupdf.Rect(s['bbox']), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE,
                              graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)

        dark_tw = pymupdf.TextWriter(page.rect)
        white_tw = pymupdf.TextWriter(page.rect)
        for s in targets:
            old = s['text'].strip()
            new = mapping[old]
            size = s['size']
            rect = pymupdf.Rect(s['bbox'])
            cx = (rect.x0 + rect.x1) / 2
            width = font.text_length(new, fontsize=size)
            baseline_y = s['origin'][1]
            tw = white_tw if s['color'] == 0xFFFFFF else dark_tw
            tw.append(pymupdf.Point(cx - width / 2, baseline_y), new, font=font, fontsize=size)
            print('p%d %-14s -> %-14s size %.1f' % (pno + 1, old, new, size))
            total += 1
        dark_tw.write_text(page, color=DARK_DEFAULT)
        white_tw.write_text(page, color=(1, 1, 1))

    doc.save(args.out, garbage=4, deflate=True)
    doc.close()
    print('replaced=%d saved %s' % (total, args.out))

    if args.png:
        d = pymupdf.open(args.out)
        for i, page in enumerate(d):
            pix = page.get_pixmap(matrix=pymupdf.Matrix(args.png, args.png), alpha=False)
            p = os.path.splitext(args.out)[0] + '_p%d.png' % (i + 1)
            pix.save(p)
            print('rendered', p, pix.width, 'x', pix.height)


if __name__ == '__main__':
    main()
