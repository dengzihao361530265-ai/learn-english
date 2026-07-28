[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

python -m PyInstaller --clean --noconfirm '背单词.spec'
python -m PyInstaller --clean --noconfirm '背单词-host.spec'

Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dist\背单词.exe') `
    -Destination (Join-Path $PSScriptRoot '背单词.exe') -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'dist\背单词-host.exe') `
    -Destination (Join-Path $PSScriptRoot '背单词-host.exe') -Force

Write-Output '构建完成：背单词.exe、背单词-host.exe'
