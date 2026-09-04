Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-Equal {
    param($Actual, $Expected, [string] $Label)
    if (-not [object]::Equals($Actual, $Expected)) {
        throw "$Label mismatch. Expected '$Expected', got '$Actual'."
    }
}

$repoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$installerPath = Join-Path $repoRoot "scripts\install-muse.ps1"
$uninstallerPath = Join-Path $repoRoot "scripts\uninstall-muse.ps1"

. $installerPath
$installerMutexName = Get-MuseLifecycleMutexName
. $uninstallerPath
$uninstallerMutexName = Get-MuseLifecycleMutexName
Assert-Equal $installerMutexName $uninstallerMutexName "shared lifecycle mutex name"

# Restore the installer functions after loading the uninstaller.
. $installerPath

$temporaryLocalAppData = Join-Path ([IO.Path]::GetTempPath()) ("fcc-muse-lifecycle-test-" + [guid]::NewGuid().ToString("N"))
$originalLocalAppData = $env:LOCALAPPDATA
$originalProcessPath = $env:Path
$script:FakeUserPath = "C:\existing-user-bin"

try {
    $env:LOCALAPPDATA = $temporaryLocalAppData
    $env:Path = "C:\existing-process-bin"

    $paths = Get-MuseInstallPaths
    New-Item -ItemType Directory -Path $paths.Bin -Force | Out-Null
    [IO.File]::WriteAllText($paths.Executable, "old")
    $previousRecord = [ordered] @{
        schema_version = 1
        owner = "free-claude-code-muse-installer"
        release_version = "0.2.1-R1"
        artifact_key = "x86_windows"
        sha256 = ("a" * 64)
        size = 3
    } | ConvertTo-Json
    [IO.File]::WriteAllText($paths.Record, $previousRecord)

    function Get-MuseNativeArchitecture { return "AMD64" }
    function Get-MuseArtifactKey { param([string] $Architecture) return "x86_windows" }
    function Get-MuseReleaseArtifact {
        param([string] $Architecture)
        return [pscustomobject] @{
            ReleaseVersion = "0.2.2-R1"
            ArtifactKey = "x86_windows"
            Url = "https://lookaside.facebook.com/muse.exe"
            Sha256 = ("b" * 64)
            Size = 3
        }
    }
    function Test-MuseManagedArtifactCurrent { return $false }
    function Save-MuseArtifact {
        param([string] $Url, [string] $Destination)
        [IO.File]::WriteAllText($Destination, "new")
    }
    function Assert-MuseArtifactIntegrity { }
    $script:CompatibilityProbeCount = 0
    function Assert-CompatibleMuseBinary {
        param([string] $Path, [string] $Context)
        $script:CompatibilityProbeCount += 1
        if ($script:CompatibilityProbeCount -ge 2) {
            throw "synthetic post-publication verification failure"
        }
    }
    function Get-MuseUserPathValue { return $script:FakeUserPath }
    function Set-MuseUserPathValue {
        param([AllowEmptyString()][string] $Value)
        $script:FakeUserPath = $Value
    }

    $failedAsExpected = $false
    try {
        Invoke-MuseInstaller
    }
    catch {
        if ($_.Exception.Message -notmatch "synthetic post-publication verification failure") {
            throw
        }
        $failedAsExpected = $true
    }
    if (-not $failedAsExpected) {
        throw "Expected the synthetic post-publication verification failure."
    }

    Assert-Equal ([IO.File]::ReadAllText($paths.Executable)) "old" "executable rollback"
    Assert-Equal ([IO.File]::ReadAllText($paths.Record)) $previousRecord "ownership rollback"
    Assert-Equal $script:FakeUserPath "C:\existing-user-bin" "user PATH rollback"
    Assert-Equal $env:Path "C:\existing-process-bin" "process PATH rollback"

    # A separately owned mutex with the same name must block an uninstaller-side acquire.
    $mutexName = Get-MuseLifecycleMutexName
    $holderScript = @'
param([string] $Name, [string] $Signal)
$mutex = [Threading.Mutex]::new($false, $Name)
$acquired = $mutex.WaitOne(5000)
if (-not $acquired) { exit 2 }
[IO.File]::WriteAllText($Signal, "held")
Start-Sleep -Seconds 3
$mutex.ReleaseMutex()
$mutex.Dispose()
'@
    $holderPath = Join-Path $temporaryLocalAppData "hold-mutex.ps1"
    $signalPath = Join-Path $temporaryLocalAppData "mutex-held.txt"
    [IO.File]::WriteAllText($holderPath, $holderScript)
    $holderArguments = @("-NoProfile", "-File", $holderPath, $mutexName, $signalPath) |
        ForEach-Object { ConvertTo-MuseNativeArgument -Argument ([string] $_) }
    $holder = Start-Process `
        -FilePath (Get-Process -Id $PID).Path `
        -ArgumentList ($holderArguments -join " ") `
        -PassThru
    try {
        $deadline = [DateTime]::UtcNow.AddSeconds(5)
        while (-not (Test-Path -LiteralPath $signalPath) -and [DateTime]::UtcNow -lt $deadline) {
            Start-Sleep -Milliseconds 50
        }
        if (-not (Test-Path -LiteralPath $signalPath)) {
            throw "Mutex holder did not become ready."
        }

        . $uninstallerPath
        $blocked = $false
        try {
            $unexpected = Enter-MuseLifecycleLock -TimeoutMilliseconds 150
            Exit-MuseLifecycleLock -Mutex $unexpected
        }
        catch {
            if ($_.Exception.Message -match "Timed out waiting") {
                $blocked = $true
            }
            else {
                throw
            }
        }
        if (-not $blocked) {
            throw "Installer and uninstaller did not contend on the same mutex."
        }
    }
    finally {
        $holder.WaitForExit()
        $holder.Dispose()
    }
}
finally {
    $env:LOCALAPPDATA = $originalLocalAppData
    $env:Path = $originalProcessPath
    Remove-Item -LiteralPath $temporaryLocalAppData -Recurse -Force -ErrorAction SilentlyContinue
}
