# -*- coding: utf-8 -*-
"""验收转曲 PDF：确认无残留文字对象、无字体资源、页数与页面尺寸与源一致。

用法:
    python verify_outlined_pdf.py <outlined.pdf> [--src <原稿.pdf|.ai>]

原理: PyMuPDF 的 get_text/get_fonts 会递归解析 Form XObject 内的文字，
比"第一页 textFrames.length==0"或"首页提不出字"可靠得多。
"""
import argparse

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('outlined')
    ap.add_argument('--src', default=None, help='源文件，用于核对页数与页面尺寸')
    args = ap.parse_args()

    doc = pymupdf.open(args.outlined)
    ok = True
    for pno, page in enumerate(doc):
        text = page.get_text().strip()
        fonts = page.get_fonts()
        n_text_ops = sum(1 for b in page.get_text('rawdict')['blocks'] if b['type'] == 0)
        status = []
        if text:
            ok = False
            status.append('残留文字 %d 字符: %r' % (len(text), text[:60]))
        if fonts:
            ok = False
            status.append('字体资源仍在: %s' % [f[3] for f in fonts][:4])
        print('page %d | text_chars=%d | text_blocks=%d | fonts=%d %s' % (
            pno + 1, len(text), n_text_ops, len(fonts),
            ('OK' if not status else '| ' + '; '.join(status))))

    if args.src:
        src = pymupdf.open(args.src)
        if len(src) != len(doc):
            ok = False
            print('页数不一致: src=%d outlined=%d' % (len(src), len(doc)))
        for i in range(min(len(src), len(doc))):
            sw, sh = round(src[i].rect.width, 1), round(src[i].rect.height, 1)
            ow, oh = round(doc[i].rect.width, 1), round(doc[i].rect.height, 1)
            if (sw, sh) != (ow, oh):
                ok = False
                print('page %d 尺寸不一致: src %dx%d vs outlined %dx%d' % (i + 1, sw, sh, ow, oh))

    print('RESULT:', 'PASS（全部转曲、无字体残留）' if ok else 'FAIL（见上行明细）')
    raise SystemExit(0 if ok else 1)


if __name__ == '__main__':
    main()
