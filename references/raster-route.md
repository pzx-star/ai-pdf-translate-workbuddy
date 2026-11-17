# 位图路线：擦除 + 重绘（文字已烧进位图 / PDF 已转曲且拿不到源文件时）

适用信号：`analyze_file.py` 报 no extractable text，或文本 span 为空但页面有整图。
产物是位图 PDF（文字不可编辑）。能拿到未转曲 .ai 时一律走矢量或原生路线。

## 流程

1. **渲染**：`pymupdf` 以 3x Matrix 渲染每页 PNG（坐标都以该倍率为基准，最后写回 PDF 时用 --scale 换算）。
2. **分析**：`ViewImage` 看渲染图，记录每个英文词的样式（颜色/字号/位置）与背景特征。
3. **检测包围盒**：`python scripts/detect_text_boxes.py render.png --y-range 300 930`，
   输出 `[x1,y1,x2,y2]` 列表；再用 ViewImage 对照核对、手工修正。
4. **采样文字色**：取框内最暗像素中位数（RGB）。
5. **擦除重绘**：写 items.json 后
   `python scripts/raster_erase_redraw.py render.png out.png --items items.json --font C:\\Windows\\Fonts\\msyhbd.ttc --pdf src.pdf out.pdf`
6. **验证**：ViewImage 检查残留英文/重影/色块/文字居中，逐项过（**每次输出换新文件名，ViewImage 对同名覆盖文件可能返回缓存图**）。

## 关键经验

- **擦除必须用 inpaint，禁止纯色填充**：`roi[mask] = bg` 的老做法在渐变底上一定留色块
  （页面背景、胶囊都是渐变的）。统一用 `cv2.inpaint(bgr, mask, 5, INPAINT_TELEA)` 从周围重建背景。
- **只定位文字像素，不整框擦**：默认模式定位"中性暗色像素"（亮度 < 205 且通道差 < 65），
  5x5 膨胀一轮吃掉抗锯齿边；不要把整个包围盒填掉——会破坏邻近插图。
- **白字在彩色底上**（如紫色胶囊里的白标题）：items.json 加 `"mask_color": "<胶囊底色hex>"`。
  脚本取胶囊最大连通域的**外轮廓**圈定范围，擦其中"非底色"像素（文字是底色掩码里的洞，
  ⚠️ 不能拿底色像素掩码直接当擦除区——那是用同色涂底，等于没擦）。
- **中文排版**：逐字 `draw.textlength` 计宽、`anchor='mm'` 居中绘制，词间距 8px、标题间距 12px；
  字号≈原框高。中文字体用 `C:\\Windows\\Fonts\\msyhbd.ttc`（微软雅黑 Bold）或思源黑体。
- **颜色顺序**：OpenCV 是 BGR，PIL 是 RGB，hex 颜色进 OpenCV 前要 `[::-1]` 翻转。
- **PDF 回包**：新建同尺寸页面（用原 PDF 的 `page.rect` 的 pt 尺寸）+ `insert_image` 整页贴图。
- 整套 50 张卡片批量时：同版式卡片坐标一致，items.json 可复用，只需换渲染图。

## items.json 字段

| 字段 | 必填 | 说明 |
|---|---|---|
| box | ✓ | `[x1,y1,x2,y2]`，基于渲染图倍率 |
| text | ✓ | 译文 |
| color |  | 译文颜色 hex（RGB）；省略则自动采样原文字色 |
| mask_color |  | 底色 hex：启用胶囊模式（白字彩底用），定位外轮廓内的非底色像素 |
| erase_color |  | 文字色 hex：按颜色定位文字（阈值 300，适合与背景差异大的字） |
| font_size |  | 默认 box 高度 |
| spacing |  | 字间距，默认 8 |
