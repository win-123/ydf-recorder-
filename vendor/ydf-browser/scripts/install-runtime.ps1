$ErrorActionPreference = "Stop"

function Get-PathEntryKey([string]$Entry) {
  if ([string]::IsNullOrWhiteSpace($Entry)) {
    return $null
  }
  $Expanded = [Environment]::ExpandEnvironmentVariables($Entry.Trim().Trim([char]34))
  try {
    $FullPath = [IO.Path]::GetFullPath($Expanded)
  }
  catch {
    $FullPath = $Expanded
  }
  return $FullPath.TrimEnd([char]92, [char]47).ToUpperInvariant()
}

function Add-UniquePathEntry([string]$PathValue, [string]$Entry) {
  $EntryKey = Get-PathEntryKey $Entry
  if (-not $EntryKey) {
    throw "PATH entry must not be empty."
  }
  $Entries = if ([string]::IsNullOrEmpty($PathValue)) { @() } else { @($PathValue.Split([char]59)) }
  $UpdatedEntries = @()
  $Found = $false
  foreach ($Existing in $Entries) {
    if ((Get-PathEntryKey $Existing) -eq $EntryKey) {
      if ($Found) {
        continue
      }
      $Found = $true
    }
    $UpdatedEntries += $Existing
  }
  if (-not $Found) {
    $UpdatedEntries += $Entry
  }
  return ($UpdatedEntries -join ";")
}

$PackageRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Version = (Get-Content (Join-Path $PackageRoot "VERSION") -Raw).Trim()
$InstallRoot = if ($env:YDF_BROWSER_HOME) { $env:YDF_BROWSER_HOME } else { Join-Path $HOME ".ydf-browser" }
$ReleaseDir = Join-Path (Join-Path $InstallRoot "releases") $Version
$CurrentPointer = Join-Path $InstallRoot "current.txt"
$VenvDir = Join-Path (Join-Path $ReleaseDir "runtime") ".venv"

New-Item -ItemType Directory -Force -Path $ReleaseDir | Out-Null
if ((Resolve-Path $PackageRoot).Path -ne (Resolve-Path $ReleaseDir -ErrorAction SilentlyContinue)) {
  Copy-Item -Path (Join-Path $PackageRoot "*") -Destination $ReleaseDir -Recurse -Force
}

function Find-Python311 {
  $Candidates = @(
    @{ Command = "python3.14"; Args = @() },
    @{ Command = "python3.13"; Args = @() },
    @{ Command = "python3.12"; Args = @() },
    @{ Command = "python3.11"; Args = @() },
    @{ Command = "python3"; Args = @() },
    @{ Command = "python"; Args = @() },
    @{ Command = "py"; Args = @("-3.14") },
    @{ Command = "py"; Args = @("-3.13") },
    @{ Command = "py"; Args = @("-3.12") },
    @{ Command = "py"; Args = @("-3.11") }
  )
  foreach ($Candidate in $Candidates) {
    $Resolved = Get-Command $Candidate.Command -ErrorAction SilentlyContinue
    if (-not $Resolved) {
      continue
    }
    & $Resolved.Source @($Candidate.Args) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" *> $null
    if ($LASTEXITCODE -eq 0) {
      return @{ Source = $Resolved.Source; Args = $Candidate.Args }
    }
  }
  return $null
}

$Python = Find-Python311
if (-not $Python) {
  throw "Python 3.11+ is required but was not found in PATH."
}

if (Test-Path $VenvDir) {
  Remove-Item $VenvDir -Force -Recurse
}
& $Python.Source @($Python.Args) -m venv $VenvDir
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"
& $VenvPython -m pip install --upgrade pip

$Wheel = Get-ChildItem -Path (Join-Path $ReleaseDir "wheels") -Filter "ydf_browser-*.whl" -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $Wheel) {
  throw "Missing ydf-browser wheel under $ReleaseDir\wheels. Build the release package with scripts/package_release.py --build-wheel."
}

& $VenvPython -m pip install --force-reinstall --find-links (Join-Path $ReleaseDir "wheels") $Wheel.FullName
& $VenvPython -m playwright install chromium

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
Set-Content -Path $CurrentPointer -Encoding ASCII -Value $ReleaseDir

$ConfigDir = Join-Path $InstallRoot "config"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$ConfigFile = Join-Path $ConfigDir "env.yaml"
if (-not (Test-Path $ConfigFile)) {
  Copy-Item -Path (Join-Path $ReleaseDir "config\env.example.yaml") -Destination $ConfigFile
}

$BinDir = if ($env:YDF_BROWSER_BIN_DIR) { $env:YDF_BROWSER_BIN_DIR } else { Join-Path $InstallRoot "bin" }
if ($BinDir.Contains(";")) {
  throw "YDF_BROWSER_BIN_DIR must not contain a semicolon."
}
$BinDir = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($BinDir))
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$CmdTarget = Join-Path $BinDir "ydf-browser.cmd"
Set-Content -Path $CmdTarget -Encoding ASCII -Value "@echo off`r`nset /p RELEASE_ROOT=<`"$CurrentPointer`"`r`ncall `"%RELEASE_ROOT%\bin\ydf-browser.cmd`" %*`r`nexit /b %ERRORLEVEL%`r`n"

$EnvironmentKey = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey("Environment")
try {
  $UserPathExists = $EnvironmentKey.GetValueNames() -contains "Path"
  $UserPath = if ($UserPathExists) {
    [string]$EnvironmentKey.GetValue("Path", "", [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
  }
  else {
    ""
  }
  $UserPathKind = if ($UserPathExists) {
    $EnvironmentKey.GetValueKind("Path")
  }
  else {
    [Microsoft.Win32.RegistryValueKind]::ExpandString
  }
  if ($UserPathKind -notin @([Microsoft.Win32.RegistryValueKind]::String, [Microsoft.Win32.RegistryValueKind]::ExpandString)) {
    throw "User PATH has an unsupported registry value type: $UserPathKind"
  }
  $UpdatedUserPath = Add-UniquePathEntry $UserPath $BinDir
  if ($UpdatedUserPath -cne $UserPath) {
    $EnvironmentKey.SetValue("Path", $UpdatedUserPath, $UserPathKind)
  }
}
finally {
  $EnvironmentKey.Dispose()
}
$env:Path = Add-UniquePathEntry $env:Path $BinDir

Write-Host "Installed ydf-browser $Version at $ReleaseDir"
Write-Host "Config file: $ConfigFile"
Write-Host "Command wrapper written to $CmdTarget"
Write-Host "Command directory registered in the current user PATH: $BinDir"
Write-Host "Run: ydf-browser doctor"
