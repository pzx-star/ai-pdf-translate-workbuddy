// 转曲源 AI 流程模板（有 Illustrator 时，转曲 PDF / 转曲 .ai 输入的固定路由）
// 用法：复制本文件，把 {{PLACEHOLDER}} 填好后经 COM DoJavaScript 执行
// （run_jsx.ps1 失败时用 ReadAllText+DoJavaScript）。
// 职责：1) 源是 .pdf 时转 base .ai（一次，CONVERT=true）；源是已转曲 .ai 时直接当 base（CONVERT=false）
//       2) 每语言删转曲字形+建译文文本框  3) 存 .ai + 转曲 .pdf
//
// ⚠️ 模板选择按「转曲与否」不按文件类型：未转曲的源（有活 textFrames）要用
//    translate_native_template.jsx 标准模板，不要用本文件的删路径逻辑（活文本没有
//    字形路径可删，原文会残留）。
//
// ⚠️ 关键坑（均已踩过）：
// - 坐标系：AI 打开 PDF 后 DOCUMENT 坐标系原点左下、y 向上，geometricBounds=[left,top,right,bottom]
//   且 top>bottom。pymupdf 的 y 从页顶向下 → ai_top = H - pdf_y_top, ai_bottom = H - pdf_y_bottom
//   （转曲 .ai 输入时先用 pymupdf 读其 PDF 兼容流取词区，同样换算）
// - CMYKColor 取值 0-100 百分比！black=100 才是纯黑，black=1 只是 1% 黑（≈白）
// - app.textFonts.itemByName 全部抛 No such element，必须 findFont 遍历 name 匹配
// - 直接用数字下标访问集合（doc.textFrames[5]）在部分版本抛 No such element，用循环取
// - 失败的 JSX 会留下未保存文档，脚本开头要 while(app.documents.length>0) close
// - AI 回写过的文件可能被进程锁，覆盖保存 Permission denied 时先改名移走旧文件
// - 源 .ai 是转曲文件时不要做 PDF→AI 转换（CONVERT=false，BASE=SRC），否则 AI 会当
//   PDF 重导入一遍再存 .ai，多此一举且可能弹导入对话框

#target illustrator

var SRC    = "{{SRC_FILE}}";       // 源文件绝对路径（正斜杠）：转曲 .pdf 或转曲 .ai
var BASE   = "{{BASE_AI}}";        // base .ai 路径（CONVERT=false 时必须等于 SRC）
var CONVERT = {{CONVERT}};         // true=源是 .pdf 需转换；false=源已是 .ai，直接当 base
var OUTDIR = "{{OUT_DIR}}";
var TS     = "{{YYYYMMDD}}";
var LOGF   = "{{LOG_TXT}}";

// 每语言：name 输出名、font AI 字体名（findFont 匹配）、items 译文案
// rect 为 AI 坐标 [left, top, right, bottom]（y 向上，已换算）；k: 1=黑(会乘100) 0=白
// maxw: 容器内宽 pt，超宽按比例缩字号（0=不缩）
// bl（可选）: 目标基线 AI y 坐标；below（可选）: 译文墨迹低于基线的距离 pt
//   ——两者由驱动端用 fontTools 从字体轮廓预计算（原字形路径底边最小值=原基线）。
//   给了 bl/below 就做【基线对齐】（与"AI 输入保留原基线"行为一致，强烈推荐）；
//   否则退回墨迹中心对齐（CJK 会与基线行为差 3~7pt）
var LANGS = [
//  {name:"{{LANG_NAME}}", font:"{{AI_FONT_NAME}}",
//   items:[ {rect:[72,155,120,173], text:"{{TEXT}}", size:18, k:1, maxw:106},
//           {rect:[197,283,274,266], text:"{{TITLE}}", size:23, k:0, maxw:92} ]},
];

var LOG = [];
function log(s) { LOG.push(s); }
function collect(items, arr) {
    for (var i = 0; i < items.length; i++) {
        var it = items[i];
        arr.push(it);
        if (it.typename == "GroupItem") collect(it.pageItems, arr);
    }
}
function findFont(nm) {
    for (var i = 0; i < app.textFonts.length; i++)
        if (app.textFonts[i].name == nm) return app.textFonts[i];
    return null;
}
try {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    while (app.documents.length > 0) app.documents[0].close(SaveOptions.DONOTSAVECHANGES);

    // 1) PDF -> AI 转换（仅 CONVERT=true 且 base 不存在时；转曲 .ai 输入时 CONVERT=false，BASE=SRC）
    if (CONVERT && !new File(BASE).exists) {
        var d0 = app.open(new File(SRC));
        var aiOpts = new IllustratorSaveOptions();
        aiOpts.pdfCompatible = true;
        d0.saveAs(new File(BASE), aiOpts);
        d0.close(SaveOptions.DONOTSAVECHANGES);
        log("CONVERTED " + BASE);
    }

    // 2) 每语言
    for (var li = 0; li < LANGS.length; li++) {
        var L = LANGS[li];
        var doc = app.open(new File(BASE));
        var rects = [];
        for (var ii = 0; ii < L.items.length; ii++) rects.push(L.items[ii].rect);

        // 删除区域内的转曲字形路径（只删 Path/CompoundPath，绝不碰图）
        var all = [];
        for (var la = 0; la < doc.layers.length; la++) collect(doc.layers[la].pageItems, all);
        var toDel = [];
        for (var i = 0; i < all.length; i++) {
            var it = all[i];
            if (it.typename != "PathItem" && it.typename != "CompoundPathItem") continue;
            var b = it.geometricBounds; // [left, top, right, bottom]
            for (var j = 0; j < rects.length; j++) {
                var r = rects[j];
                if (b[0] >= r[0] - 2.5 && b[2] <= r[2] + 2.5 &&
                    b[1] <= r[1] + 2.5 && b[3] >= r[3] - 2.5) {
                    toDel.push(it);
                    break;
                }
            }
        }
        for (var i = 0; i < toDel.length; i++) toDel[i].remove();
        log(L.name + " deleted=" + toDel.length);

        // 建译文文本框
        var font = findFont(L.font);
        if (!font) throw new Error("font not found: " + L.font);
        for (var ii = 0; ii < L.items.length; ii++) {
            var it = L.items[ii];
            var r = it.rect;
            var cx = (r[0] + r[2]) / 2, cy = (r[1] + r[3]) / 2;
            var tf = doc.textFrames.add();
            tf.contents = it.text;
            var tr = tf.textRange;
            tr.characterAttributes.size = it.size;
            tr.characterAttributes.textFont = font;
            var col = new CMYKColor();
            col.cyan = 0; col.magenta = 0; col.yellow = 0; col.black = it.k * 100;
            tr.characterAttributes.fillColor = col;
            // 原文带透明度状态时按需设 tf.opacity = 90
            var gb = tf.geometricBounds;
            var w = gb[2] - gb[0];
            if (it.maxw && w > it.maxw) {
                tr.characterAttributes.size = Math.max(6, it.size * it.maxw / w);
            }
            // 定位（不要用行框中心！行框因 CJK 字体行高偏移，日语会压低十几 pt）：
            // 首选基线对齐——复制一份转曲量实测墨迹 bbox，墨迹底 + below = 实际基线，
            // 平移使基线 = it.bl（与 AI 输入路线保留原基线的行为一致）；
            // 无 bl/below 时退回墨迹中心对齐。
            var placed = false;
            try {
                var dup = tf.duplicate();
                var g = dup.createOutline(); // 转曲副本，返回 GroupItem
                var ib = g.geometricBounds;  // 转曲后真实墨迹 [l,t,r,b]
                if (it.bl !== undefined && it.below !== undefined) {
                    var bl_ai = ib[3] + it.below; // 墨迹底 + 低于基线量 = 基线
                    tf.translate(cx - (ib[0] + ib[2]) / 2, it.bl - bl_ai);
                } else {
                    tf.translate(cx - (ib[0] + ib[2]) / 2, cy - (ib[1] + ib[3]) / 2);
                }
                g.remove();
                placed = true;
            } catch (eInk) {}
            if (!placed) {
                // 兜底：行框中心（拉丁字体近似可用）
                gb = tf.geometricBounds;
                tf.top = cy + (gb[1] - gb[3]) / 2;
                tf.left = cx - (gb[2] - gb[0]) / 2;
            }
        }
        log(L.name + " added=" + L.items.length);

        // 存 .ai（可编辑）
        var aiOpts2 = new IllustratorSaveOptions();
        aiOpts2.pdfCompatible = true;
        doc.saveAs(new File(OUTDIR + "/{{SRC_NAME}}_" + L.name + "_" + TS + ".ai"), aiOpts2);
        // 同一文档转曲 + 存 .pdf
        var outlined = 0;
        for (var ti = doc.textFrames.length - 1; ti >= 0; ti--) {
            try { doc.textFrames[ti].createOutline(); outlined++; } catch (e) {}
        }
        var pdfOpts = new PDFSaveOptions();
        doc.saveAs(new File(OUTDIR + "/{{SRC_NAME}}_" + L.name + "_" + TS + ".pdf"), pdfOpts);
        doc.close(SaveOptions.DONOTSAVECHANGES);
        log("SAVED " + L.name + " ai+pdf | outlined=" + outlined);
    }
    log("ALL DONE");
} catch (e) {
    log("ERROR: " + e.message + " (line " + e.line + ")");
}
var f = new File(LOGF);
f.open("w"); f.encoding = "UTF-8"; f.writeln(LOG.join("\n")); f.close();
