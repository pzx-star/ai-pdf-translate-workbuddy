# -*- coding: utf-8 -*-
"""在高分辨率页面渲染图上检测深色文字条带，输出候选包围盒（供 raster_erase_redraw.py 使用）。

用法:
    python detect_text_boxes.py <render.png> [--min-h 8] [--gap-x 35] [--y-range y0 y1]

原理: 中性暗色（低饱和、偏暗）像素 -> 行投影找条带 -> 条带内 x 投影找词组 -> 小间隙合并。
输出的 box 需人工/目视核对后再用（可用 ViewImage 看渲染图对照）。
"""
import argparse

import cv2
import numpy as np


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--min-h', type=int, default=8, help='条带最小高度(px)')
    ap.add_argument('--min-w', type=int, default=15, help='词组最小宽度(px)')
    ap.add_argument('--gap-x', type=int, default=35, help='词组合并的最大 x 间隙')
    ap.add_argument('--y-range', type=int, nargs=2, default=None, help='只在该 y 范围内检测')
    args = ap.parse_args()

    im = cv2.imdecode(np.fromfile(args.image, dtype=np.uint8), cv2.IMREAD_COLOR)  # 支持中文路径
    mx = im.max(axis=2)
    mn = im.min(axis=2)
    dark = ((mx < 140) & ((mx - mn) < 45)).astype(np.uint8)

    y0, y1 = args.y_range if args.y_range else (0, im.shape[0])
    rows = (dark.sum(axis=1) > 3).astype(int)
    d = np.diff(np.r_[0, rows, 0])
    starts = np.where(d == 1)[0]
    ends = np.where(d == -1)[0] - 1

    import json
    boxes = []
    for s, e in zip(starts, ends):
        if e - s < args.min_h or not (y0 <= s and e <= y1):
            continue
        sub = dark[s:e + 1]
        col = (sub.sum(axis=0) > 0).astype(int)
        d2 = np.diff(np.r_[0, col, 0])
        ss = np.where(d2 == 1)[0]
        ee = np.where(d2 == -1)[0] - 1
        groups = []
        for a, b in zip(ss, ee):
            if groups and a - groups[-1][1] < args.gap_x:
                groups[-1][1] = b
            else:
                groups.append([int(a), int(b)])
        for a, b in groups:
            if b - a > args.min_w:
                boxes.append([int(a), int(s), int(b), int(e)])

    print(json.dumps(boxes, ensure_ascii=False))
    print('# found %d boxes (x1,y1,x2,y2), 基于 %s' % (len(boxes), args.image))


if __name__ == '__main__':
    main()
