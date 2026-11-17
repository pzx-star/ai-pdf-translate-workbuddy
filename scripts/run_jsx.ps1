# 通过 COM 驱动 Adobe Illustrator 执行 JSX 脚本，并回读日志。
# 用法: powershell -File run_jsx.ps1 <script.jsx> [log.txt]
# 注意: 若报 "COM object instantiation can run arbitrary code"，是 WorkBuddy 命令安全检查器拦截，
#       需在 Illustrator 豁免补丁生效的会话中运行（见 references/illustrator-automation.md）。
param(
    [Parameter(Mandatory = $true)][string]$Jsx,
    [string]$Log
)
$ErrorActionPreference = 'Stop'
try {
    $ai = New-Object -ComObject Illustrator.Application
    Write-Output ("COM OK version=" + $ai.Version)
    $null = $ai.DoJavaScriptFile((Resolve-Path $Jsx).Path)
    Write-Output "JSX done"
} catch {
    Write-Output ("ERROR: " + $_.Exception.Message)
    exit 1
}
if ($Log -and (Test-Path $Log)) {
    Write-Output "--- log ---"
    Get-Content $Log
}
