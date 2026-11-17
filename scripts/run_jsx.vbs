' Illustrator JSX 启动器（Windows）：cscript //nologo run_jsx.vbs <脚本.jsx>
' 用 cscript 走 COM，无需修改 WorkBuddy 的 PowerShell 安全规则。
' JSX 以 UTF-8 读入后经 DoJavaScript 传递，避免路径/编码问题。
On Error Resume Next
If WScript.Arguments.Count < 1 Then
  WScript.Echo "用法：cscript //nologo run_jsx.vbs <脚本.jsx> [日志文件]"
  WScript.Quit 2
End If
jsxPath = WScript.Arguments(0)
logFile = ""
If WScript.Arguments.Count > 1 Then logFile = WScript.Arguments(1)

Set fso = CreateObject("Scripting.FileSystemObject")
If Not fso.FileExists(jsxPath) Then
  WScript.Echo "找不到 JSX 文件：" & jsxPath
  WScript.Quit 2
End If

Set app = GetObject(, "Illustrator.Application")
If Err.Number <> 0 Then
  Err.Clear
  Set app = CreateObject("Illustrator.Application")
End If
If Err.Number <> 0 Then
  WScript.Echo "无法启动 Illustrator COM：" & Err.Description
  WScript.Quit 3
End If
WScript.Echo "COM OK version=" & app.Version

Set stream = CreateObject("ADODB.Stream")
stream.Type = 2
stream.Charset = "utf-8"
stream.Open
stream.LoadFromFile jsxPath
js = stream.ReadText
stream.Close

Err.Clear
result = app.DoJavaScript(js)
If Err.Number <> 0 Then
  WScript.Echo "JSX 执行失败：" & Err.Description
  WScript.Quit 4
End If
WScript.Echo "JSX done"

If logFile <> "" And fso.FileExists(logFile) Then
  WScript.Echo "--- log ---"
  WScript.Echo fso.OpenTextFile(logFile, 1).ReadAll
End If
