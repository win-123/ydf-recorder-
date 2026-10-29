$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$ManifestUri = [Uri]"https://061981.xyz/ydf-browser/release-manifest.json"
$TrustedHost = "061981.xyz"
$UserAgent = "ydf-browser-installer/1"

function Test-TrustedUri([Uri]$Uri) {
  return $Uri.Scheme -eq "https" -and $Uri.Host -eq $TrustedHost -and -not $Uri.UserInfo
}

function Get-EffectiveUri($Response) {
  if ($Response.BaseResponse -and $Response.BaseResponse.ResponseUri) {
    return [Uri]$Response.BaseResponse.ResponseUri
  }
  if ($Response.BaseResponse -and $Response.BaseResponse.RequestMessage -and $Response.BaseResponse.RequestMessage.RequestUri) {
    return [Uri]$Response.BaseResponse.RequestMessage.RequestUri
  }
  throw "Could not determine the final response URL."
}

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

function Convert-ManifestVersion($Value, [string]$Name) {
  $Parsed = $null
  if (-not [Version]::TryParse([string]$Value, [ref]$Parsed)) {
    throw "Release manifest $Name is invalid."
  }
  return $Parsed
}

$Python = Find-Python311
if (-not $Python) {
  throw "Python 3.11+ is required but was not found in PATH."
}

$TempRoot = Join-Path ([IO.Path]::GetTempPath()) ("ydf-browser-install-" + [Guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $TempRoot | Out-Null

try {
  $ManifestFile = Join-Path $TempRoot "release-manifest.json"
  $ManifestResponse = Invoke-WebRequest -UseBasicParsing -Uri $ManifestUri -OutFile $ManifestFile -PassThru -MaximumRedirection 5 -UserAgent $UserAgent
  $ManifestEffectiveUri = Get-EffectiveUri $ManifestResponse
  if (-not (Test-TrustedUri $ManifestEffectiveUri)) {
    throw "Release manifest redirected to an untrusted URL."
  }

  $Manifest = Get-Content $ManifestFile -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($Manifest.schema_version -ne 1) {
    throw "Unsupported release manifest schema_version."
  }
  if ($Manifest.channel -ne "stable") {
    throw "Release manifest channel must be stable."
  }
  $ReleaseVersion = Convert-ManifestVersion $Manifest.version "version"
  $MinimumPython = Convert-ManifestVersion $Manifest.min_python "min_python"
  $null = Convert-ManifestVersion $Manifest.min_skill_version "min_skill_version"
  $CurrentPythonText = (& $Python.Source @($Python.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
  if ($LASTEXITCODE -ne 0) {
    throw "Could not read the current Python version."
  }
  $CurrentPython = [Version]$CurrentPythonText
  if ($CurrentPython -lt $MinimumPython) {
    throw "Python $MinimumPython+ is required; current version is $CurrentPython."
  }

  $PackageProperties = @($Manifest.platforms.PSObject.Properties)
  if ($PackageProperties.Count -eq 0) {
    throw "Release manifest platforms must not be empty."
  }
  $Packages = @{}
  foreach ($Property in $PackageProperties) {
    $PackageUri = $null
    if (-not [Uri]::TryCreate([string]$Property.Value.url, [UriKind]::Absolute, [ref]$PackageUri) -or -not (Test-TrustedUri $PackageUri)) {
      throw "Release package URL is untrusted or not HTTPS: $($Property.Name)"
    }
    $Sha256 = ([string]$Property.Value.sha256).ToLowerInvariant()
    if ($Sha256 -notmatch "^[0-9a-f]{64}$") {
      throw "Release package sha256 is invalid: $($Property.Name)"
    }
    $Packages[$Property.Name] = @{ Uri = $PackageUri; Sha256 = $Sha256 }
  }

  $Machine = switch ($env:PROCESSOR_ARCHITECTURE) {
    "AMD64" { "x86_64" }
    "ARM64" { "arm64" }
    default { $env:PROCESSOR_ARCHITECTURE.ToLowerInvariant() }
  }
  $SelectedPackage = $null
  foreach ($Candidate in @("windows-$Machine", "windows", "all")) {
    if ($Packages.ContainsKey($Candidate)) {
      $SelectedPackage = $Packages[$Candidate]
      break
    }
  }
  if (-not $SelectedPackage) {
    throw "Release manifest has no package for this platform."
  }

  $ArchiveFile = Join-Path $TempRoot "release.zip"
  $PackageResponse = Invoke-WebRequest -UseBasicParsing -Uri $SelectedPackage.Uri -OutFile $ArchiveFile -PassThru -MaximumRedirection 5 -UserAgent $UserAgent
  $PackageEffectiveUri = Get-EffectiveUri $PackageResponse
  if (-not (Test-TrustedUri $PackageEffectiveUri)) {
    throw "Release package redirected to an untrusted URL."
  }
  $ActualSha256 = (Get-FileHash -Path $ArchiveFile -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($ActualSha256 -ne $SelectedPackage.Sha256) {
    throw "Release package SHA-256 verification failed."
  }

  $ExtractRoot = Join-Path $TempRoot "package"
  New-Item -ItemType Directory -Path $ExtractRoot | Out-Null
  Add-Type -AssemblyName System.IO.Compression.FileSystem
  $Archive = [IO.Compression.ZipFile]::OpenRead($ArchiveFile)
  try {
    $RootPrefix = [IO.Path]::GetFullPath($ExtractRoot + [IO.Path]::DirectorySeparatorChar)
    foreach ($Entry in $Archive.Entries) {
      $Relative = $Entry.FullName.Replace("\", "/")
      $Parts = @($Relative.Split("/") | Where-Object { $_ -ne "" })
      if ([IO.Path]::IsPathRooted($Relative) -or $Parts -contains "..") {
        throw "Release package contains a path outside the extraction root."
      }
      $Destination = [IO.Path]::GetFullPath((Join-Path $ExtractRoot ($Relative.Replace("/", [IO.Path]::DirectorySeparatorChar))))
      if (-not $Destination.StartsWith($RootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Release package contains a path outside the extraction root."
      }
      $UnixMode = ($Entry.ExternalAttributes -shr 16) -band 0xF000
      if ($UnixMode -eq 0xA000) {
        throw "Release package contains an unsupported symbolic link."
      }
    }
  }
  finally {
    $Archive.Dispose()
  }
  [IO.Compression.ZipFile]::ExtractToDirectory($ArchiveFile, $ExtractRoot)

  $Entries = @(Get-ChildItem -LiteralPath $ExtractRoot)
  if ($Entries.Count -eq 1 -and $Entries[0].PSIsContainer -and -not (Test-Path (Join-Path $ExtractRoot "VERSION"))) {
    $PackageRoot = $Entries[0].FullName
  }
  else {
    $PackageRoot = $ExtractRoot
  }
  if (-not (Test-Path (Join-Path $PackageRoot "VERSION") -PathType Leaf)) {
    throw "Release package is missing VERSION."
  }
  $PackageVersion = (Get-Content (Join-Path $PackageRoot "VERSION") -Raw -Encoding UTF8).Trim()
  if ($PackageVersion -ne $ReleaseVersion.ToString()) {
    throw "Release package VERSION does not match the release manifest: $PackageVersion != $ReleaseVersion"
  }
  if (@(Get-ChildItem (Join-Path $PackageRoot "wheels") -Filter "ydf_browser-*.whl" -ErrorAction SilentlyContinue).Count -eq 0) {
    throw "Release package is missing the ydf-browser wheel."
  }
  $RuntimeInstaller = Join-Path $PackageRoot "scripts\install-runtime.ps1"
  if (-not (Test-Path $RuntimeInstaller -PathType Leaf)) {
    throw "Release package is missing the Windows runtime installer."
  }

  & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $RuntimeInstaller
  if ($LASTEXITCODE -ne 0) {
    throw "Windows runtime installer failed: exit_code=$LASTEXITCODE"
  }

  $InstallRoot = if ($env:YDF_BROWSER_HOME) { $env:YDF_BROWSER_HOME } else { Join-Path $HOME ".ydf-browser" }
  $BinDir = if ($env:YDF_BROWSER_BIN_DIR) { $env:YDF_BROWSER_BIN_DIR } else { Join-Path $InstallRoot "bin" }
  if ($BinDir.Contains(";")) {
    throw "YDF_BROWSER_BIN_DIR must not contain a semicolon."
  }
  $BinDir = [IO.Path]::GetFullPath([Environment]::ExpandEnvironmentVariables($BinDir))
  $env:Path = Add-UniquePathEntry $env:Path $BinDir
  Write-Host "Optional skill installation:"
  Write-Host "  ydf-browser install-skill"
  Write-Host "Command available in this PowerShell: ydf-browser doctor"
  Write-Host "Installed stable ydf-browser runtime $ReleaseVersion."
}
finally {
  if (Test-Path $TempRoot) {
    Remove-Item $TempRoot -Force -Recurse
  }
}
