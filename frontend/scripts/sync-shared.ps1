<#
  sync-shared.ps1 — 共享 → 三端同步脚本（Windows PowerShell 主用）

  作用：
    1. 清空 user-app/common、band-portal/common、admin-console/common
    2. 把 frontend/shared/ 全部内容复制到三端 common/
    3. 对三端 common/ 与 shared/ 计算 SHA256 哈希并比对，drift != 0 报错退出

  约定：任何人不得直接改三端 common/；只改 shared/，改完必须跑本脚本。
  用法：powershell -ExecutionPolicy Bypass -File sync-shared.ps1
#>
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot          # frontend/
$shared = Join-Path $root 'shared'
$targets = @('user-app', 'band-portal', 'admin-console')

if (-not (Test-Path $shared)) {
  Write-Error "shared 目录不存在: $shared"
  exit 1
}

Write-Host '== 清空并复制 shared → 三端 common/ =='
foreach ($t in $targets) {
  $common = Join-Path $root (Join-Path $t 'common')
  if (Test-Path $common) {
    Remove-Item -Recurse -Force $common
  }
  New-Item -ItemType Directory -Path $common -Force | Out-Null
  Copy-Item -Path (Join-Path $shared '*') -Destination $common -Recurse -Force
  Write-Host ("  [ok] {0}/common/ ({1} 项)" -f $t, (Get-ChildItem -Path $common -Recurse -File).Count)
}

Write-Host '== 哈希一致性校验（drift 检测）=='

function Get-FileHashMap([string]$dir) {
  $map = @{}
  Get-ChildItem -Path $dir -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($dir.Length).TrimStart('\', '/')
    $map[$rel] = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
  }
  return $map
}

# 基线 = shared/ 自身（比 user-app 更可靠，避免「两处同步错误互相同意」）
$baseline = Get-FileHashMap $shared
$drift = 0

foreach ($t in $targets) {
  $common = Join-Path $root (Join-Path $t 'common')
  $map = Get-FileHashMap $common

  if ($map.Count -ne $baseline.Count) {
    Write-Host ("  [FAIL] {0}: 文件数不一致 (shared={1}, {0}= {2})" -f $t, $baseline.Count, $map.Count)
    $drift++
    continue
  }

  foreach ($rel in $baseline.Keys) {
    if (-not $map.ContainsKey($rel)) {
      Write-Host "  [FAIL] $t 缺少 $rel"
      $drift++
    } elseif ($map[$rel] -ne $baseline[$rel]) {
      Write-Host "  [FAIL] $t 内容不一致: $rel"
      $drift++
    }
  }

  if ($drift -eq 0) {
    Write-Host "  [ok] $t common/ 与 shared/ 一致"
  }
}

if ($drift -gt 0) {
  Write-Host ''
  Write-Host "sync-shared FAILED: drift = $drift"
  exit 1
}

Write-Host ''
Write-Host 'sync-shared OK: 三端 common/ 与 shared/ 完全一致 (drift=0)'
