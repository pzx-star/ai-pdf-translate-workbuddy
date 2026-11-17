/*
 * 转曲导出：在文档副本中把所有画板全部文字转为轮廓，导出矢量多页 PDF。
 * ⚠️ 只在副本上操作；原 .ai 保持文字可编辑。
 * 用法：填 SRC（已翻译的 .ai）、AI_COPY（临时转曲版，放 work）、DST_PDF、LOG，
 * 然后 run_jsx.ps1 / run_jsx.vbs 执行。
 * 验收：verify_outlined_pdf.py 确认输出无文字对象、无字体资源、页数一致。
 */
#target illustrator

var SRC     = "G:/path/to/translated.ai";
var AI_COPY = "G:/path/to/work/translated_转曲.ai";
var DST_PDF = "G:/path/to/output/translated_转曲.pdf";
var LOG     = "G:/path/to/work/outline_log.txt";

var lines = [];
function log(s) { lines.push(s); }

function writeLog() {
    var f = new File(LOG);
    f.open("w"); f.encoding = "UTF-8";
    f.writeln(lines.join("\\n"));
    f.close();
}

/* 解锁全部图层与对象（副本上才做） */
function unlockAll(doc) {
    for (var i = 0; i < doc.layers.length; i++) {
        doc.layers[i].locked = false;
        doc.layers[i].visible = true;
    }
    var items = doc.pageItems;
    for (var j = 0; j < items.length; j++) {
        try { items[j].locked = false; } catch (e) {}
        try { items[j].hidden = false; } catch (e) {}
    }
}

try {
    app.userInteractionLevel = UserInteractionLevel.DONTDISPLAYALERTS;
    var doc = app.open(new File(SRC));
    unlockAll(doc);

    /* 倒序遍历：createOutline 会替换原对象，倒序避免索引失效 */
    var total = doc.textFrames.length;
    log("textFrames=" + total);
    for (var i = total - 1; i >= 0; i--) {
        try { doc.textFrames[i].createOutline(); }
        catch (e) { log("  SKIP #" + i + ": " + e.message); }
    }
    log("outlined=" + (total - skippedCount(lines)) + " remaining=" + doc.textFrames.length);

    /* 副本存为转曲版 AI（通常不交付，仅留档 work） */
    doc.saveAs(new File(AI_COPY), new IllustratorSaveOptions());

    /* 导出全部画板的多页 PDF，关闭 Illustrator 编辑能力（纯矢量转曲交付） */
    var opt = new PDFSaveOptions();
    try { opt.preserveEditability = false; } catch (e) {}
    doc.saveAs(new File(DST_PDF), opt);
    doc.close(SaveOptions.DONOTSAVECHANGES);
    log("DONE -> " + DST_PDF);
} catch (e) {
    log("ERROR: " + e.message + " (line " + e.line + ")");
}
writeLog();

/* 统计 SKIP 条数（简单遍历） */
function skippedCount(arr) {
    var n = 0;
    for (var k = 0; k < arr.length; k++) if (arr[k].charAt(0) === ' ' && arr[k].indexOf("SKIP") === 1) n++;
    return n;
}
