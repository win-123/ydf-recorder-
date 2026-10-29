$ErrorActionPreference = "Stop"

$Target = if ($args.Count -gt 0) { $args[0] } else { "all" }
$PackageRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$SkillSource = Join-Path $PackageRoot "skills\gov-ydfdev-browser"
$SkillVersionPath = Join-Path $PackageRoot "VERSION"
$AgentsHome = if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { Join-Path $HOME ".agents" }
$ClaudeHome = if ($env:CLAUDE_HOME) { $env:CLAUDE_HOME } else { Join-Path $HOME ".claude" }
$AgentsRoot = Join-Path $AgentsHome "skills"
$Canonical = Join-Path $AgentsRoot "gov-ydfdev-browser"
$ClaudeDest = Join-Path (Join-Path $ClaudeHome "skills") "gov-ydfdev-browser"
$NeedsClaude = $false

switch ($Target) {
  "agents" {}
  "codex" {}
  "claude" { $NeedsClaude = $true }
  "all" { $NeedsClaude = $true }
  default {
    throw "Usage: install-skill.ps1 [codex|claude|agents|all]"
  }
}

if (-not (Test-Path -LiteralPath (Join-Path $SkillSource "SKILL.md") -PathType Leaf) -or
    -not (Test-Path -LiteralPath $SkillVersionPath -PathType Leaf)) {
  throw "Incomplete gov-ydfdev-browser skill source in $PackageRoot"
}
$SkillVersion = (Get-Content $SkillVersionPath -Raw).Trim()
if (-not $SkillVersion) {
  throw "Empty VERSION in $PackageRoot"
}

$ClaudeItem = Get-Item -LiteralPath $ClaudeDest -Force -ErrorAction SilentlyContinue
if ($NeedsClaude -and $null -ne $ClaudeItem -and
    -not ($ClaudeItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint)) {
  throw "Refusing to replace non-link Claude Code skill target: $ClaudeDest"
}

New-Item -ItemType Directory -Force -Path $AgentsRoot | Out-Null
$Stage = Join-Path $AgentsRoot (".gov-ydfdev-browser." + [guid]::NewGuid().ToString("N"))
try {
  Copy-Item -LiteralPath $SkillSource -Destination $Stage -Recurse -Force
  Set-Content -LiteralPath (Join-Path $Stage "VERSION") -Encoding ASCII -Value $SkillVersion
  $CanonicalItem = Get-Item -LiteralPath $Canonical -Force -ErrorAction SilentlyContinue
  if ($null -ne $CanonicalItem) {
    if ($CanonicalItem.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
      Remove-Item -LiteralPath $Canonical -Force
    }
    else {
      Get-ChildItem -LiteralPath $Canonical -Force -Recurse -File | ForEach-Object { $_.IsReadOnly = $false }
      Remove-Item -LiteralPath $Canonical -Force -Recurse
    }
  }
  Move-Item -LiteralPath $Stage -Destination $Canonical
}
finally {
  if (Test-Path -LiteralPath $Stage) {
    Remove-Item -LiteralPath $Stage -Force -Recurse
  }
}
Write-Host "Installed gov-ydfdev-browser skill to $Canonical"

if ($NeedsClaude) {
  $LinkIsCurrent = $false
  if ($null -ne $ClaudeItem) {
    $LinkTarget = [string]$ClaudeItem.Target
    if ($LinkTarget) {
      if (-not [System.IO.Path]::IsPathRooted($LinkTarget)) {
        $LinkTarget = Join-Path $ClaudeItem.Parent.FullName $LinkTarget
      }
      $LinkIsCurrent = [System.IO.Path]::GetFullPath($LinkTarget) -eq [System.IO.Path]::GetFullPath($Canonical)
    }
  }
  if (-not $LinkIsCurrent) {
    New-Item -ItemType Directory -Force -Path (Split-Path $ClaudeDest -Parent) | Out-Null
    if ($null -ne $ClaudeItem) {
      Remove-Item -LiteralPath $ClaudeDest -Force
    }
    New-Item -ItemType Junction -Path $ClaudeDest -Target $Canonical | Out-Null
  }
  Write-Host "Linked Claude Code skill at $ClaudeDest"
}

Write-Host "Restart your agent tool to pick up new skills."
