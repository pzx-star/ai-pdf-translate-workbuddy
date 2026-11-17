# -*- coding: utf-8 -*-
"""位图擦除重绘：擦掉页面渲染图上指定包围盒内的文字（inpaint 从周围重建背景），在原位置绘制译文。

用法:
    python raster_erase_redraw.py <render.png> <out.png> --items items.json --font C:\\Windows\\Fonts\\msyhbd.ttc [--pdf <src.pdf> <out.pdf>] [--scale 3]

items.json 示例（坐标基于 --scale 倍渲染图）:
[
  {"box": [217, 426, 357, 476], "text": "苹果"},
  {"box": [592, 95, 821, 145],  "text": "字母", "color": "#ffffff", "mask_color": "#9b8ec4"}
]

color 省略时自动采样: 取 box 内最暗 20% 像素的中位色。
擦除策略: 三种模式都只定位"文字像素"，然后用 cv2.inpaint 从周围重建背景——
保留渐变，不留色块。纯色 roi[mask]=bg 的老做法在渐变底上会留下明显色块，已废弃。

⚠️ 生成 PDF 时整页转为位图（文字不可编辑），仅在拿不到未转曲源文件时使用。
"""
import argparse
import json
import os

import cv2
import numpy as np
import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont


def hex2rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def sample_text_color(arr, box):
    x1, y1, x2, y2 = box
    roi = arr[y1:y2 + 1, x1:x2 + 1].reshape(-1, 3)
    order = np.argsort(roi.max(axis=1))
    pick = order[:max(1, len(order) // 5)]          # 最暗 20%，不足则取 1 像素
    return tuple(int(v) for v in np.median(roi[pick], axis=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('render')
    ap.add_argument('out')
    ap.add_argument('--items', required=True)
    ap.add_argument('--font', required=True)
    ap.add_argument('--pdf', nargs=2, metavar=('SRC_PDF', 'OUT_PDF'))
    ap.add_argument('--pdf-patch', nargs=2, metavar=('SRC_PDF', 'OUT_PDF'),
                    help='补丁式回写：原 PDF 保持原样，只把擦除重绘区域贴回原位置（保色彩/保其余内容）')
    ap.add_argument('--scale', type=int, default=3, help='render.png 相对 PDF 的倍率')
    ap.add_argument('--inpaint-r', type=int, default=5, help='inpaint 半径')
    ap.add_argument('--feather', type=int, default=10,
                    help='补丁回写时透明边缘的羽化跨度（px，渲染图坐标）')
    args = ap.parse_args()

    with open(args.items, encoding='utf-8') as f:
        items = json.load(f)

    # PIL 读图，规避 cv2 中文路径问题
    img = Image.open(args.render).convert('RGB')
    arr = np.array(img)
    out = arr.copy()
    out_bgr = cv2.cvtColor(out, cv2.COLOR_RGB2BGR)
    # 记录所有被改动过的像素（擦除+inpaint 邻域），补丁回写只贴这些像素
    touched = np.zeros(out_bgr.shape[:2], np.uint8)

    for it in items:
        x1, y1, x2, y2 = it['box']
        pad = 6
        X1, Y1 = max(0, x1 - pad), max(0, y1 - pad)
        X2, Y2 = min(out.shape[1] - 1, x2 + pad), min(out.shape[0] - 1, y2 + pad)
        roi = out_bgr[Y1:Y2 + 1, X1:X2 + 1]
        if it.get('mask_color'):
            # 纯色底上的文字（如彩色胶囊里的白字）：定位底色连通域外轮廓内的"非底色"像素
            # （文字+抗锯齿+阴影都是底色掩码中的"洞"）。
            # ⚠️ 必须用外轮廓圈定范围再取洞，不能拿底色像素掩码当擦除区——那只是用同色涂底。
            target = np.array(hex2rgb(it['mask_color']))
            near = (np.abs(out_bgr.astype(int) - target[::-1]).sum(axis=2) < 150).astype(np.uint8)
            win = np.zeros_like(near)
            win[Y1:Y2 + 1, X1:X2 + 1] = near[Y1:Y2 + 1, X1:X2 + 1]
            n, lab, stats, _ = cv2.connectedComponentsWithStats(win, 8)
            big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            region = np.zeros_like(win)
            contours, _ = cv2.findContours((lab == big).astype(np.uint8),
                                           cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(region, contours, -1, 1, -1)
            mask = region.astype(bool) & (near == 0)
        elif it.get('erase_color'):
            # 按文字颜色定位（阈值 300 = BGR 三通道绝对差之和，吃掉抗锯齿中间调）
            target = np.array(hex2rgb(it['erase_color']))[::-1]
            mask = (np.abs(roi.astype(int) - target).sum(axis=2) < 300).astype(bool)
        else:
            # 默认：中性暗色文字（含抗锯齿边缘）
            mean = roi.mean(axis=2)
            spread = roi.max(axis=2) - roi.min(axis=2)
            mask = (mean < 205) & (spread < 65)

        mask = cv2.dilate(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        if it.get('mask_color'):
            mask = mask[Y1:Y2 + 1, X1:X2 + 1]

        # inpaint 修复（而非纯色填充）：保留背景渐变，不留色块
        full_mask = np.zeros(out_bgr.shape[:2], np.uint8)
        full_mask[Y1:Y2 + 1, X1:X2 + 1] = mask.astype(np.uint8)
        out_bgr = cv2.inpaint(out_bgr, full_mask, args.inpaint_r, cv2.INPAINT_TELEA)
        # inpaint 会波及掩码边缘邻域，扩大 touched 覆盖范围
        touched = np.maximum(touched, cv2.dilate(full_mask, np.ones(
            (args.inpaint_r * 2 + 1, args.inpaint_r * 2 + 1), np.uint8)))
        print('erase %s pixels=%d mode=%s (inpaint r=%d)' % (
            it['box'], int(mask.sum()),
            'mask' if it.get('mask_color') else ('color' if it.get('erase_color') else 'dark'),
            args.inpaint_r))

    out = cv2.cvtColor(out_bgr, cv2.COLOR_BGR2RGB)
    draw = ImageDraw.Draw(img := Image.fromarray(out))
    for it in items:
        x1, y1, x2, y2 = it['box']
        color = hex2rgb(it['color']) if it.get('color') else sample_text_color(arr, it['box'])
        size = it.get('font_size', y2 - y1)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + 1
        spacing = it.get('spacing', 8)
        text = it['text']
        latin = all(ord(c) < 0x2E80 for c in text)  # 拉丁/西里尔等西方文字整词绘制；CJK 才逐字
        # 可选：限制总宽（渲染图像素），超出则按比例收缩字号——防长译文溢出压到插图
        max_w = it.get('max_width')
        if max_w:
            probe = ImageFont.truetype(args.font, size)
            widths = [draw.textlength(ch, font=probe) for ch in text]
            total = sum(widths) + spacing * (len(text) - 1)
            if total > max_w:
                size = max(10, int(size * max_w / total))
        font = ImageFont.truetype(args.font, size)
        widths = [draw.textlength(ch, font=font) for ch in text]
        total = sum(widths) + spacing * (len(text) - 1)
        if latin:
            # 拉丁/西里尔整词绘制：字距由字体 kerning 决定，视觉与原版一致
            draw.text((cx, cy), text, font=font, fill=color, anchor='mm')
            it['_real_bbox'] = [int(v) for v in draw.textbbox((cx, cy), text, font=font, anchor='mm')]
        else:
            x = cx - total / 2
            bb = [int(cx - total / 2), int(cy), int(cx + total / 2), int(cy)]
            for ch, w in zip(text, widths):
                draw.text((x + w / 2, cy), ch, font=font, fill=color, anchor='mm')
                cb = draw.textbbox((x + w / 2, cy), ch, font=font, anchor='mm')
                bb = [min(bb[0], cb[0]), min(bb[1], cb[1]), max(bb[2], cb[2]), max(bb[3], cb[3])]
                x += w + spacing
            it['_real_bbox'] = bb
        print('draw %r at (%.0f, %.0f) color=%s size=%d' % (text, cx, cy, color, size))

    img.save(args.out)
    print('saved', args.out)

    if args.pdf:
        src_pdf, out_pdf = args.pdf
        src = pymupdf.open(src_pdf)
        rect = src[0].rect
        doc = pymupdf.open()
        page = doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(page.rect, filename=args.out)
        doc.save(out_pdf, garbage=3, deflate=True)
        print('saved', out_pdf, '(%dx%d pt, 位图版)' % (rect.width, rect.height))

    if args.pdf_patch:
        import io
        src_pdf, out_pdf = args.pdf_patch
        src = pymupdf.open(src_pdf)
        page = src[0]
        k = args.scale
        # 羽化透明叠加：只有被改动过的像素（擦除区 ∪ 绘制的文字）不透明，
        # 边缘高斯羽化渐变，其余 alpha=0 完全露出原图——
        # 彻底消除"补丁矩形与 CMYK 原图轻微色差形成的淡框/接缝"。
        alpha = Image.new('L', img.size, 0)
        ad = ImageDraw.Draw(alpha)
        boxes = []
        for it in items:
            bx1, by1, bx2, by2 = it['box']
            rb = it.get('_real_bbox', (bx1, by1, bx2, by2))
            x1, y1 = min(bx1, rb[0]), min(by1, rb[1])
            x2, y2 = max(bx2, rb[2]), max(by2, rb[3])
            ad.rectangle([x1, y1, x2, y2], fill=255)
            boxes.append((max(0, x1), max(0, y1),
                          min(img.width - 1, x2), min(img.height - 1, y2)))
        a_np = np.maximum(np.array(alpha), touched * 255)
        a_img = Image.fromarray(a_np).filter(
            ImageFilter.GaussianBlur(max(2, args.feather / 2)))
        rgba = img.convert('RGBA')
        rgba.putalpha(a_img)
        pad = args.feather * 3  # 覆盖羽化过渡带
        for (x1, y1, x2, y2) in boxes:
            cx1, cy1 = max(0, x1 - pad), max(0, y1 - pad)
            cx2, cy2 = min(img.width - 1, x2 + pad), min(img.height - 1, y2 + pad)
            crop = rgba.crop((cx1, cy1, cx2 + 1, cy2 + 1))
            buf = io.BytesIO()
            crop.save(buf, 'PNG')
            rect = pymupdf.Rect(cx1 / k, cy1 / k, (cx2 + 1) / k, (cy2 + 1) / k)
            page.insert_image(rect, stream=buf.getvalue())
        src.save(out_pdf, garbage=3, deflate=True)
        print('saved', out_pdf, '(羽化透明叠加回写, 未改动像素保持原样)')


if __name__ == '__main__':
    main()
