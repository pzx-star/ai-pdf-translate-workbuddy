# -*- coding: utf-8 -*-
"""多语言翻译台账：每个文字对象一行，每种目标语言一列。每个源文件只维护一个 XLSX。

用法:
    # 初始化（提取全部文字对象，生成空表）
    python make_translation_xlsx.py src.ai 卡片翻译.xlsx

    # 填入某种语言的译文（mapping.json: 原文->译文），已存在的表会按对象编号更新该语言列
    python make_translation_xlsx.py src.ai 卡片翻译.xlsx --lang fr --map fr.json

    # 再加一种语言，继续对同一张表跑 --lang es 即可；旧译文不会丢失

规则:
- 对象编号 = p<页码>-<序号>，按页内出现顺序，跨语言稳定对齐；不按原文字串合并不同对象。
- 主表「翻译对照」只放参与翻译（已替换/待翻译）的对象；
  无映射对象（页码、品牌名等不翻译内容）单独放「无映射对象」sheet。
- 后续某语言补上了映射，对象会自动从「无映射对象」移回主表。
- 状态列记录: 已替换 / 待翻译 / 未处理（轮廓字、图片内文字等如实标记）。
"""
import argparse
import json
import os
import time
import time

import pymupdf

HEAD = ['对象编号', '页码', '字体', '字号', '状态', '备注', '源语言', '原文']
MAIN_SHEET = '翻译对照'
UNMAPPED_SHEET = '无映射对象'


def extract_objects(src):
    doc = pymupdf.open(src)
    rows = []
    for pno, page in enumerate(doc):
        idx = 0
        for b in page.get_text('dict')['blocks']:
            if b['type'] != 0:
                continue
            for line in b['lines']:
                for s in line['spans']:
                    t = s['text'].strip()
                    if not t:
                        continue
                    idx += 1
                    rows.append({
                        'id': 'p%d-%d' % (pno + 1, idx),
                        'page': pno + 1,
                        'text': t,
                        'font': s['font'],
                        'size': round(s['size'], 1),
                    })
    return rows


def index_rows(ws):
    """按对象编号建立 {id: 行号} 索引。"""
    out = {}
    for r in range(2, ws.max_row + 1):
        oid = ws.cell(r, 1).value
        if oid:
            out[oid] = r
    return out


def style_sheet(ws, col_of):
    from openpyxl.styles import Alignment
    ws.freeze_panes = 'A2'
    for name, w in [('对象编号', 10), ('页码', 6), ('源语言', 8), ('原文', 24),
                    ('字体', 22), ('字号', 7), ('状态', 10), ('备注', 18)]:
        if name in col_of:
            ws.column_dimensions[ws.cell(1, col_of[name]).column_letter].width = w
    for h, c in col_of.items():
        if h not in HEAD:
            ws.column_dimensions[ws.cell(1, c).column_letter].width = 18
    if '原文' in col_of:
        for r in range(2, ws.max_row + 1):
            ws.cell(r, col_of['原文']).alignment = Alignment(wrap_text=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('src')
    ap.add_argument('xlsx')
    ap.add_argument('--lang', default=None, help='本次填入的目标语言列名，如 fr')
    ap.add_argument('--map', default=None, help='该语言的 mapping.json（原文->译文）')
    ap.add_argument('--seed', default=None,
                    help='对象种子 JSON（[{page,text,font,size},...]）。转曲/位图源提取不到文字对象时，'
                         '用已核对的文字清单建行；状态列标"转曲-重建"')
    args = ap.parse_args()

    from openpyxl import Workbook, load_workbook
    from openpyxl.styles import Font as XLFont

    # xlsx 参数若为目录，自动命名: 源文件名_翻译_日期.xlsx，并按源类型路由到 <dir>/ai 或 <dir>/pdf
    if os.path.isdir(args.xlsx):
        is_ai = args.src.lower().endswith('.ai')
        base = os.path.splitext(os.path.basename(args.src))[0]
        ts = time.strftime('%Y%m%d')
        sub = os.path.join(args.xlsx, 'ai' if is_ai else 'pdf')
        os.makedirs(sub, exist_ok=True)
        args.xlsx = os.path.join(sub, '%s_\u7ffb\u8bd1_%s.xlsx' % (base, ts))
        print('output xlsx:', args.xlsx)

    rows = extract_objects(args.src)
    seeds = []
    if args.seed:
        with open(args.seed, encoding='utf-8') as f:
            seeds = json.load(f)
        if seeds:
            # 转曲/位图源：以人工核对的对象清单建行（与提取行合并去重）
            # 原字体无法确定时默认 Arial Rounded MT Bold（除非 seed 显式给出 font）
            known = {r['text'] for r in rows}
            for i, s in enumerate(seeds, len(rows) + 1):
                if s['text'] in known:
                    continue
                rows.append({'id': 'p%d-%d' % (s.get('page', 1), i),
                             'page': s.get('page', 1),
                             'text': s['text'],
                             'font': s.get('font') or 'Arial Rounded MT Bold',
                             'size': s.get('size', '')})
    lang = args.lang

    if os.path.isfile(args.xlsx):
        wb = load_workbook(args.xlsx)
    else:
        wb = Workbook()
        wb.active.title = MAIN_SHEET
        wb.active.append(HEAD)
    if MAIN_SHEET not in wb.sheetnames:
        wb.create_sheet(MAIN_SHEET).append(HEAD)
    ws = wb[MAIN_SHEET]
    if UNMAPPED_SHEET not in wb.sheetnames:
        wb.create_sheet(UNMAPPED_SHEET).append(HEAD)
    wu = wb[UNMAPPED_SHEET]

    col_of = {ws.cell(1, c).value: c for c in range(1, ws.max_column + 1) if ws.cell(1, c).value}
    print('已有台账: 主表 %d 行 %d 列 | 无映射 %d 行' % (ws.max_row - 1, len(col_of), wu.max_row - 1))

    if lang and lang not in col_of:
        ws.cell(1, ws.max_column + 1, lang)
        col_of[lang] = ws.max_column
    if lang:
        ws.cell(1, col_of[lang]).font = XLFont(bold=True)

    mapping = {}
    if args.map:
        with open(args.map, encoding='utf-8') as f:
            mapping = json.load(f)

    main_idx = index_rows(ws)
    unm_idx = index_rows(wu)
    moved = 0
    seed_texts = {s['text'] for s in (seeds or [])} if args.seed else set()

    def status_for(text):
        return '转曲-重建' if text in seed_texts else '待翻译'

    for row in rows:
        oid = row['id']
        mapped = lang is not None and row['text'] in mapping

        if mapped:
            # 主表确保存在
            if oid in main_idx:
                r = main_idx[oid]
            else:
                ws.append([oid, row['page'], row['font'], row['size'], status_for(row['text']),
                           '转曲源，字形位置人工核对重建' if row['text'] in seed_texts else '',
                           'en', row['text']])
                r = ws.max_row
                main_idx[oid] = r
            ws.cell(r, col_of[lang], mapping[row['text']])
            st = col_of.get('状态')
            if st:
                ws.cell(r, st, '已替换')
            # 从无映射表移除
            if oid in unm_idx:
                wu.delete_rows(unm_idx[oid], 1)
                unm_idx = index_rows(wu)
                moved += 1
        elif lang is not None and not mapped:
            # 本次语言无此映射：若已在主表（别的语言翻过）则保持不动；
            # 否则进「无映射对象」表
            if oid in main_idx:
                st = col_of.get('状态')
                if st and ws.cell(main_idx[oid], st).value == '待翻译' and \
                        not ws.cell(main_idx[oid], col_of[lang]).value:
                    ws.cell(main_idx[oid], col_of[lang], '')
                continue
            if oid not in unm_idx:
                wu.append([oid, row['page'], row['font'], row['size'],
                           '未翻译-保留原文', '不参与翻译（如页码/品牌名）', 'en', row['text']])
                unm_idx[oid] = wu.max_row
        else:
            # 初始化（无 --lang）：全部进主表
            if oid not in main_idx:
                ws.append([oid, row['page'], row['font'], row['size'], status_for(row['text']),
                           '转曲源，字形位置人工核对重建' if row['text'] in seed_texts else '',
                           'en', row['text']])
                main_idx[oid] = ws.max_row

    style_sheet(ws, col_of)
    style_sheet(wu, {h: i + 1 for i, h in enumerate(HEAD)})

    wb.save(args.xlsx)
    print('saved %s | objects=%d | lang=%s | 主表 %d 行 | 无映射 %d 行 | 移回主表 %d'
          % (args.xlsx, len(rows), lang, ws.max_row - 1, wu.max_row - 1, moved))


if __name__ == '__main__':
    main()
