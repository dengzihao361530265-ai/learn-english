[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'TouchFish\BeidanciChrome')
)

$ErrorActionPreference = 'Stop'
$registryKey = 'HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.touchfish.beidanci'
if (Test-Path -LiteralPath $registryKey) {
    Remove-Item -LiteralPath $registryKey -Force
}
if (Test-Path -LiteralPath $InstallRoot -PathType Container) {
    $resolved = [IO.Path]::GetFullPath($InstallRoot)
    $expected = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA 'TouchFish\BeidanciChrome'))
    if ($resolved -ne $expected) {
        throw "拒绝删除非默认目录：$resolved"
    }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
Write-Output 'Chrome 扩展 Native Host 注册与本地扩展副本已移除。'
