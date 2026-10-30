# skills/mcgyvr/install.ps1: put the /mcgyvr, /mcgyvr-direct and /mcgyvr-use
# skills where a harness will find them, on Windows.
#
# The twin of install.sh, for a machine with PowerShell and no bash: the same
# three skills, copied byte for byte (each SKILL.md and the `references/` beside
# it) into the same two harness folders under the user's home (the Claude CLI's
# `.claude\skills`, pi's `.pi\agent\skills`), with the same digest record beside
# each copy, the same version floor and the same lines on stdout. Every setting
# below is held to install.sh's by tests/test_install_ps1_is_the_twin_of_install_sh.py.
# What install.sh's comments say of each step holds here too.
#
# Windows PowerShell 5.1 and PowerShell 7 both run it, and neither needs
# administrator. Where the execution policy refuses every script, run it for
# this one session only (a `git clone` carries no downloaded-file mark, so
# RemoteSigned runs it and changes no setting):
#
#   powershell -NoProfile -ExecutionPolicy RemoteSigned -File mcgyvr\skills\mcgyvr\install.ps1
#
# The file is ASCII only: Windows PowerShell 5.1 reads a script with no BOM in
# the ANSI code page, so where install.sh prints an em dash this prints "-".
#
# The home is %USERPROFILE% on Windows and $HOME elsewhere, read from the
# environment so a test can point the install somewhere else.
#
# Installing twice changes nothing. Uninstalling twice is not an error.

Set-StrictMode -Version 3.0
$ErrorActionPreference = "Stop"

$SkillsRoot = Split-Path -Parent $PSScriptRoot
$Checkout = Split-Path -Parent $SkillsRoot

$Skills = @(
  "mcgyvr",
  "mcgyvr-direct",
  "mcgyvr-use"
)
$HarnessDirs = @(
  ".claude/skills",
  ".pi/agent/skills"
)
$SetupDoc = "skills/mcgyvr/SETUP.md"
$CliInstall = "uv tool install mcgyvr"
$MinVersion = "0.5.1"
$RepoUrl = "https://github.com/AdarGit008/mcgyvr"
$Record = ".mcgyvr-installed"
$DescriptionMax = 1024

$Utf8 = New-Object System.Text.UTF8Encoding($false)

function Get-UserHome {
  if ($env:OS -eq "Windows_NT" -and $env:USERPROFILE) { return $env:USERPROFILE }
  if ($env:HOME) { return $env:HOME }
  return [Environment]::GetFolderPath("UserProfile")
}

# A path under `$Base` named with forward slashes, as the settings and the
# record name them, in this system's separator.
function Join-Rel([string]$Base, [string]$Rel) {
  return Join-Path $Base ($Rel -replace "/", [IO.Path]::DirectorySeparatorChar)
}

$ExamplesMd = Join-Rel $SkillsRoot "mcgyvr-direct/references/examples.md"

function Write-Err([string]$Text) {
  [Console]::Error.WriteLine($Text)
}

function Stop-Install([string]$Text, [int]$Code = 1) {
  Write-Err $Text
  exit $Code
}

function Get-Digest([string]$Path) {
  return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path).Hash.ToLowerInvariant()
}

function Get-Unquoted([string]$Text) {
  $s = $Text.Trim()
  if ($s.Length -ge 2 -and (($s[0] -eq '"' -and $s[-1] -eq '"') -or ($s[0] -eq "'" -and $s[-1] -eq "'"))) {
    return $s.Substring(1, $s.Length - 2)
  }
  return $s
}

function Test-Skill([string]$File, [string]$ExpectedName) {
  $lines = [IO.File]::ReadAllLines($File, $Utf8)
  if ($lines.Count -eq 0 -or $lines[0].Trim() -ne "---") {
    Stop-Install "install.ps1: ${File}: frontmatter must open the file"
  }
  $end = -1
  for ($i = 1; $i -lt $lines.Count; $i++) {
    if ($lines[$i].Trim() -eq "---") { $end = $i; break }
  }
  if ($end -lt 0) {
    Stop-Install "install.ps1: ${File}: frontmatter is not closed by a second ---"
  }
  $name = ""
  $description = ""
  for ($i = 1; $i -lt $end; $i++) {
    $line = $lines[$i]
    if ($line.StartsWith("name:")) { $name = Get-Unquoted $line.Substring(5) }
    elseif ($line.StartsWith("description:")) { $description = Get-Unquoted $line.Substring(12) }
  }
  if ($name -cne $ExpectedName) {
    Stop-Install "install.ps1: ${File}: frontmatter name '$name' is not the directory it lands in ('$ExpectedName')"
  }
  if (-not $description) {
    Stop-Install "install.ps1: ${File}: frontmatter has no description"
  }
  if ($description.Length -gt $DescriptionMax) {
    Stop-Install "install.ps1: ${File}: description is $($description.Length) characters, over the $DescriptionMax a harness will read"
  }
}

# Every file the install writes for one skill, relative to its directory, with
# forward slashes as install.sh records them: SKILL.md and its references.
function Get-Payload([string]$From) {
  $files = @("SKILL.md")
  $references = Join-Path $From "references"
  if (Test-Path -LiteralPath $references -PathType Container) {
    foreach ($item in (Get-ChildItem -LiteralPath $references -File | Sort-Object Name)) {
      $files += "references/$($item.Name)"
    }
  }
  return ,$files
}

# Whether a record names a file inside the skill folder: relative, with no
# `..` part. Anything else is not this script's, and is neither checked nor
# removed.
function Test-Inside([string]$Rel) {
  if ([IO.Path]::IsPathRooted($Rel) -or $Rel.Contains(":")) { return $false }
  foreach ($part in ($Rel -split "[\\/]")) {
    if ($part -eq "..") { return $false }
  }
  return $true
}

function Read-Record([string]$Dest) {
  $path = Join-Path $Dest $Record
  $entries = @()
  if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { return ,$entries }
  foreach ($line in [IO.File]::ReadAllLines($path, $Utf8)) {
    if (-not $line.Trim()) { continue }
    $parts = $line -split "\s+", 2
    $rel = if ($parts.Count -gt 1 -and $parts[1]) { $parts[1] } else { "SKILL.md" }
    if (-not (Test-Inside $rel)) { continue }
    $entries += , @($parts[0], $rel)
  }
  return ,$entries
}

function Test-Installed([string]$Dest) {
  foreach ($entry in (Read-Record $Dest)) {
    $file = Join-Rel $Dest $entry[1]
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
    if ((Get-Digest $file) -ne $entry[0]) {
      Stop-Install "install.ps1: $file differs from the copy this script installed; something has edited it. Re-run with --force to overwrite it."
    }
  }
}

function Remove-Dropped([string]$Dest, [string[]]$Keep) {
  foreach ($entry in (Read-Record $Dest)) {
    $rel = $entry[1]
    $file = Join-Rel $Dest $rel
    if ($Keep -contains $rel -or -not (Test-Path -LiteralPath $file -PathType Leaf)) { continue }
    Remove-Item -LiteralPath $file -Force
    Write-Output "removed: $file"
    $parent = Split-Path -Parent $file
    if ($parent -ne $Dest -and -not (Get-ChildItem -LiteralPath $parent -Force)) {
      Remove-Item -LiteralPath $parent -Force
    }
  }
}

# Runs `mcgyvr` and answers its exit code and the lines of ONE stream, as
# install.sh reads it: stdout for `--version` (stderr dropped), stderr for
# `contract` (stdout dropped). It never stops the install: a native command
# writing to stderr is not an error here.
function Invoke-Mcgyvr([string[]]$Arguments, [switch]$Stderr) {
  $saved = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    if ($Stderr) {
      $output = & mcgyvr @Arguments 2>&1 |
        Where-Object { $_ -is [System.Management.Automation.ErrorRecord] } |
        ForEach-Object { "$_" }
    } else {
      $output = & mcgyvr @Arguments 2>$null | ForEach-Object { "$_" }
    }
    $code = $LASTEXITCODE
  } catch {
    $output = @()
    $code = 1
  } finally {
    $ErrorActionPreference = $saved
  }
  return @{ Code = $code; Lines = @($output) }
}

# Whether the CLI on PATH accepts every contract /mcgyvr-direct ships; warns
# and answers $false when it rejects any (install.sh's probe_examples).
function Test-Examples([string]$Found) {
  if (-not (Test-Path -LiteralPath $ExamplesMd -PathType Leaf)) { return $true }
  $scratch = Join-Path ([IO.Path]::GetTempPath()) ("mcgyvr-install-" + [Guid]::NewGuid().ToString("N"))
  try {
    # A probe that cannot run (no temporary folder) warns of nothing, as
    # install.sh's does when mktemp fails.
    New-Item -ItemType Directory -Path $scratch | Out-Null
    $count = 0
    $inside = $false
    $current = $null
    foreach ($line in [IO.File]::ReadAllLines($ExamplesMd, $Utf8)) {
      if (-not $inside -and $line -eq '```yaml') {
        $count++
        $current = New-Object System.Collections.Generic.List[string]
        $inside = $true
      } elseif ($inside -and $line -eq '```') {
        [IO.File]::WriteAllText((Join-Path $scratch "example-$count.yaml"), (($current -join "`n") + "`n"), $Utf8)
        $inside = $false
      } elseif ($inside) {
        $current.Add($line)
      }
    }
    $rejected = 0
    $first = ""
    for ($i = 1; $i -le $count; $i++) {
      $ran = Invoke-Mcgyvr @("contract", (Join-Path $scratch "example-$i.yaml")) -Stderr
      if ($ran.Code -ne 0) {
        $rejected++
        if (-not $first -and $ran.Lines.Count -gt 0) { $first = $ran.Lines[0] }
      }
    }
  } catch {
    return $true
  } finally {
    Remove-Item -LiteralPath $scratch -Recurse -Force -ErrorAction SilentlyContinue
  }
  if ($rejected -eq 0) { return $true }
  $fix = "install the CLI from the same revision as this skill"
  if (Test-Path -LiteralPath (Join-Path $Checkout "pyproject.toml") -PathType Leaf) {
    $fix += ": uv tool install --force $Checkout"
  }
  if ($Found -match '^[0-9]+\.[0-9]+\.[0-9]+$') {
    $fix = "Re-install the skills from the CLI's release (git clone --depth 1 --branch v$Found $RepoUrl, then its skills\mcgyvr\install.ps1), or $fix"
  } else {
    $fix = $fix.Substring(0, 1).ToUpperInvariant() + $fix.Substring(1)
  }
  if (-not $first) { $first = "no reason given" }
  Write-Err "install.ps1: mcgyvr $Found rejects $rejected of the $count example contracts /mcgyvr-direct ships (${first}): the skills and the CLI are from different revisions, so the skill teaches contracts this CLI refuses. $fix."
  return $false
}

# The numeric release parts of a version (`0.5.1.dev3` -> 0, 5, 1), and
# whether anything followed them, for the comparison install.sh makes with
# `sort -V`.
function Get-VersionParts([string]$Version) {
  $numbers = @()
  $rest = $false
  foreach ($part in $Version.Split(".")) {
    if ($rest) { break }
    # A part's leading digits count (`1rc1` is 1, then more), as `sort -V`
    # reads them; anything after them ends the release numbers.
    if ($part -match '^([0-9]+)(.*)$') {
      $numbers += [int64]$Matches[1]
      if ($Matches[2]) { $rest = $true }
    } else {
      $rest = $true
    }
  }
  return @{ Numbers = $numbers; Rest = $rest }
}

# Whether `$Core` is older than `$MinVersion`, the way `sort -V` orders them:
# release numbers first, and a version with more after equal numbers is newer.
function Test-Older([string]$Core) {
  $have = Get-VersionParts $Core
  $want = Get-VersionParts $MinVersion
  $width = [Math]::Max($have.Numbers.Count, $want.Numbers.Count)
  for ($i = 0; $i -lt $width; $i++) {
    $a = if ($i -lt $have.Numbers.Count) { $have.Numbers[$i] } else { -1 }
    $b = if ($i -lt $want.Numbers.Count) { $want.Numbers[$i] } else { -1 }
    if ($a -lt $b) { return $true }
    if ($a -gt $b) { return $false }
  }
  return $false
}

# Warns; never fails (install.sh's check_version).
function Test-Version {
  if (-not (Get-Command mcgyvr -ErrorAction SilentlyContinue)) {
    Write-Err "install.ps1: no mcgyvr on PATH: the skills are installed, but there is nothing on this machine for them to drive. Get it with: $CliInstall"
    return
  }
  $ran = Invoke-Mcgyvr @("--version")
  $reported = ""
  if ($ran.Code -eq 0 -and $ran.Lines.Count -gt 0) { $reported = [string]$ran.Lines[0] }
  $found = ""
  if ($reported.StartsWith("mcgyvr ")) { $found = $reported.Substring(7).Trim() }
  if (-not $found) {
    Write-Err "install.ps1: mcgyvr is on PATH but did not report a version; wanted $MinVersion or newer."
    return
  }
  if (-not (Test-Examples $found)) { return }
  $core = $found.Split("+")[0]
  if ($core -eq "0.0.0") {
    Write-Err "install.ps1: mcgyvr reports ${found}: it is running from a tree that was never installed, so it has no version to check. Install it with: $CliInstall"
    return
  }
  if (Test-Older $core) {
    Write-Err "install.ps1: mcgyvr $found is older than $MinVersion, the oldest this skill is known to drive. Upgrade it with: $CliInstall"
  }
}

# Every target of every skill: the skill's name and its folder under the home.
function Get-Targets {
  $userHome = Get-UserHome
  $targets = @()
  foreach ($name in $Skills) {
    foreach ($harness in $HarnessDirs) {
      $targets += , @($name, (Join-Rel $userHome "$harness/$name"))
    }
  }
  return ,$targets
}

function Install-Skills([bool]$Force) {
  foreach ($name in $Skills) {
    $skillMd = Join-Path (Join-Path $SkillsRoot $name) "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillMd -PathType Leaf)) {
      Stop-Install "install.ps1: no SKILL.md for the $name skill ($skillMd)"
    }
    Test-Skill $skillMd $name
  }
  $targets = Get-Targets
  if (-not $Force) {
    foreach ($target in $targets) { Test-Installed $target[1] }
  }
  foreach ($target in $targets) {
    $from = Join-Path $SkillsRoot $target[0]
    $dest = $target[1]
    $payload = Get-Payload $from
    New-Item -ItemType Directory -Force -Path $dest | Out-Null
    Remove-Dropped $dest $payload
    $lines = @()
    foreach ($rel in $payload) {
      $src = Join-Rel $from $rel
      $landed = Join-Rel $dest $rel
      New-Item -ItemType Directory -Force -Path (Split-Path -Parent $landed) | Out-Null
      Copy-Item -LiteralPath $src -Destination $landed -Force
      $digest = Get-Digest $landed
      if ($digest -ne (Get-Digest $src)) {
        Stop-Install "install.ps1: ${landed}: what landed is not what was copied"
      }
      $lines += "$digest  $rel"
      Write-Output "installed: $landed"
    }
    [IO.File]::WriteAllText((Join-Path $dest $Record), (($lines -join "`n") + "`n"), $Utf8)
  }
  Write-Output "setup: $SetupDoc"
  Write-Output "cli: $CliInstall"
  Write-Output "Invoke them with /mcgyvr <prompt> or /mcgyvr-direct <files|dir>; neither loads itself."
  Test-Version
}

function Uninstall-Skills {
  $removed = $false
  foreach ($target in (Get-Targets)) {
    $dest = $target[1]
    if (Test-Path -LiteralPath $dest) {
      $item = Get-Item -LiteralPath $dest -Force
      if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        # A linked skill folder: remove the link, never what it points at
        # (Windows PowerShell's Remove-Item -Recurse would follow it), as
        # install.sh's `rm -rf` removes the link alone.
        [IO.Directory]::Delete($dest)
      } else {
        Remove-Item -LiteralPath $dest -Recurse -Force
      }
      Write-Output "removed: $dest"
      $removed = $true
    } else {
      Write-Output "not installed: $dest"
    }
  }
  if (-not $removed) { Write-Output "Nothing to remove." }
}

function Show-Usage {
  Write-Output "usage: install.ps1 [--force] [--uninstall] [--help]"
  Write-Output ""
  Write-Output "  (no args)    install /mcgyvr, /mcgyvr-direct and /mcgyvr-use for Claude CLI and pi"
  Write-Output "  --force      overwrite an installed copy that was edited by hand"
  Write-Output "  --uninstall  remove them from both"
}

$given = if ($args.Count -gt 0) { [string]$args[0] } else { "" }
switch -CaseSensitive ($given) {
  "" { Install-Skills $false }
  "--force" { Install-Skills $true }
  "--uninstall" { Uninstall-Skills }
  "--help" { Show-Usage }
  "-h" { Show-Usage }
  default { Stop-Install "install.ps1: ${given}: not an argument this understands - $SetupDoc" 2 }
}
exit 0
