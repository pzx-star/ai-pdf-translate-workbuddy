/* 用 Illustrator 把 .ai 导出为配套 PDF（与 .ai 完全同源）。
 * ⚠️ 不要设置 opt.pDFPreset = "[Illustrator Default]"——中文版 AI 会报错 'CONF'(1129270854)，不指定预设即可。
 */
#target illustrator
(function () {
    var SRC = "G:/path/to/input.ai";
    var DST = "G:/path/to/output.pdf";
    var LOG = "G:/path/to/work/export_pdf_log.txt";
    try {
        app.open(new File(SRC));
        var doc = app.activeDocument;
        doc.saveAs(new File(DST), new PDFSaveOptions());
        doc.close(SaveOptions.DONOTSAVECHANGES);
        var f = new File(LOG); f.open("w"); f.write("EXPORT DONE"); f.close();
    } catch (e) {
        var f = new File(LOG); f.open("w"); f.write("ERROR " + e); f.close();
    }
})();
