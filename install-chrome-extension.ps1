[CmdletBinding()]
param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA 'TouchFish\BeidanciChrome')
)

$ErrorActionPreference = 'Stop'
$extensionId = 'ehgcdcbighbkmeegmkiplbglcabhjiia'
$hostName = 'com.touchfish.beidanci'
$sourceExtension = Join-Path $PSScriptRoot 'chrome-extension'
$hostExe = Join-Path $PSScriptRoot '背单词-host.exe'
$envFile = Join-Path $PSScriptRoot '.env'

if (-not (Test-Path -LiteralPath $hostExe -PathType Leaf)) {
    throw "找不到 Native Host：$hostExe，请先构建背单词-host.exe。"
}

$extensionTarget = Join-Path $InstallRoot 'chrome-extension'
New-Item -ItemType Directory -Force -Path $extensionTarget | Out-Null
Copy-Item -LiteralPath (Join-Path $sourceExtension 'manifest.json') -Destination $extensionTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceExtension 'background.js') -Destination $extensionTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceExtension 'content.js') -Destination $extensionTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceExtension 'popup.html') -Destination $extensionTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceExtension 'popup.js') -Destination $extensionTarget -Force
Copy-Item -LiteralPath (Join-Path $sourceExtension 'icons') -Destination $extensionTarget -Recurse -Force

$nativeManifestPath = Join-Path $InstallRoot 'native-host-manifest.json'
$nativeManifest = [ordered]@{
    name = $hostName
    description = '划词发送到背单词'
    path = $hostExe
    type = 'stdio'
    allowed_origins = @("chrome-extension://$extensionId/")
}
$nativeManifestJson = $nativeManifest | ConvertTo-Json -Depth 3
[IO.File]::WriteAllText(
    $nativeManifestPath,
    $nativeManifestJson,
    (New-Object Text.UTF8Encoding($false))
)

$registryKey = "HKCU:\Software\Google\Chrome\NativeMessagingHosts\$hostName"
New-Item -Path $registryKey -Force | Out-Null
Set-Item -Path $registryKey -Value $nativeManifestPath

if (Test-Path -LiteralPath $envFile -PathType Leaf) {
    & icacls.exe $envFile '/inheritance:r' '/grant:r' "$($env:USERNAME):(R)" | Out-Null
}

[pscustomobject]@{
    ExtensionId = $extensionId
    ExtensionPath = $extensionTarget
    NativeHost = $hostExe
    NativeManifest = $nativeManifestPath
    RegistryKey = $registryKey
}
