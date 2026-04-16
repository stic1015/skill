[CmdletBinding()]
param(
    [int]$BackendPort = 8787
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-CommandExists {
    param([Parameter(Mandatory = $true)][string]$Name)
    $null -ne (Get-Command $Name -ErrorAction SilentlyContinue)
}

if (-not (Test-CommandExists -Name "cloudflared")) {
    Write-Error "cloudflared 未安装。请先安装 Cloudflare Tunnel 客户端，然后重试。"
}

$targetUrl = "http://127.0.0.1:$BackendPort"
Write-Output "Starting Cloudflare Quick Tunnel for $targetUrl ..."
Write-Output "请保持此窗口运行，终端中会显示 https://*.trycloudflare.com 的公开地址。"
Write-Output "将该地址填入前端页面的 '后端 API Base'，或拼到分享链接参数 api_base。"

cloudflared tunnel --url $targetUrl --no-autoupdate
