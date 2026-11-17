# -*- coding: utf-8 -*-
"""分析 PDF / .ai（PDF 兼容格式）文件：页数、文本 span（文字/字体/字号/颜色/坐标）、内嵌图片、字体列表。

用法:
    python analyze_file.py <file.pdf|.ai> [--page N] [--render 3]

--render N: 同时以 N 倍缩放渲染每页 PNG 到 <file同目录>/_analyze_p<i>.png，便于目视核对。
.ai / .pdf 未转曲时文本是活的，可直接分析；text 为空时脚本会统计矢量路径数自动区分
「转曲矢量」(走转曲模板/路线D) 与「位图」(走路线A)，并在末尾打印路由判定结论。
"""
import argparse
import os

import pymupdf


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('file')
    ap.add_argument('--page', type=int, default=None, help='只分析第 N 页（1 起）')
    ap.add_argument('--render', type=int, default=0, help='渲染倍率，0=不渲染')
    args = ap.parse_args()

    doc = pymupdf.open(args.file)
    print('file:', args.file)
    print('pages:', len(doc), '| size(bytes):', os.path.getsize(args.file))
    raw = open(args.file, 'rb').read()
    print('header:', raw[:8], '| AIPrivateData blocks:', raw.count(b'AIPrivateData'))

    pages = range(len(doc)) if args.page is None else [args.page - 1]
    any_text = False
    for pno in pages:
        page = doc[pno]
        print('\n--- page %d | rect %s | images %d ---' % (pno + 1, page.rect, len(page.get_images(full=True))))
        print('fonts:', page.get_fonts())
        text = page.get_text().strip()
        if text:
            any_text = True
        else:
            # 无活文本：区分「转曲矢量」与「位图」——统计矢量填充路径数
            try:
                drawings = [d for d in page.get_drawings() if d['type'] in ('f', 'fs')]
            except Exception:
                drawings = []
            verdict = ('转曲矢量(路径数=%d, 走转曲模板/路线D)' % len(drawings)) if drawings \
                else '位图(走路线A OCR)'
            print('(no extractable text -> %s)' % verdict)
            if drawings:
                # 打印深色/白色填充聚类，辅助确认字形
                import collections
                fills = collections.Counter()
                for d in drawings:
                    f = d.get('fill')
                    if f:
                        fills[tuple(round(c, 2) for c in f)] += 1
                print('fill clusters:', dict(fills.most_common(6)))
        for b in page.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                for s in line['spans']:
                    print('SPAN %r | font=%s size=%.2f color=%s origin=%s bbox=%s flags=%d' % (
                        s['text'], s['font'], s['size'],
                        hex(s['color']), tuple(round(v, 2) for v in s.get('origin', ())),
                        tuple(round(v, 2) for v in s['bbox']), s['flags']))

    # 末尾给出路由结论（二维：转曲与否 + 文件类型 + 是否有 Illustrator 由调用方结合）
    if args.page is None:
        ext = os.path.splitext(args.file)[1].lower()
        kind = 'ai' if ext == '.ai' else ('pdf' if ext == '.pdf' else ext)
        print('\n==== 路由判定 ====')
        print('input_type: %s' % kind)
        print('outlined: %s' % (not any_text))
        if any_text:
            print('=> 未转曲(有活文本): .ai/转后.ai 走路线C标准模板; .pdf+无AI 走路线B')
        else:
            print('=> 已转曲: .ai+有AI 走转曲模板(CONVERT=false); .pdf+有AI 转base.ai+转曲模板; 无AI 走路线D')

    if args.render:
        for pno in range(len(doc)):
            pix = doc[pno].get_pixmap(matrix=pymupdf.Matrix(args.render, args.render), alpha=False)
            out = os.path.splitext(args.file)[0] + '_analyze_p%d.png' % (pno + 1)
            pix.save(out)
            print('rendered', out, pix.width, 'x', pix.height)


if __name__ == '__main__':
    main()
