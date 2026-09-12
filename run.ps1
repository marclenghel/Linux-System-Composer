# Launch Linux System Composer on Windows.
#
#   .\run.ps1                    start the app
#   .\run.ps1 -Test              run the test suite instead
#   .\run.ps1 -Report            print the detected hardware as JSON instead
#   .\run.ps1 --dry-run DIR      say what writing a build there would do
#   .\run.ps1 --write DIR        write it
#   .\run.ps1 --rollback DIR     undo the last write in that directory
#
# Works from any directory - it moves to its own folder first, which is the
# thing that bites you when you run the app from C:\Windows\system32.
# Creates the virtual environment and installs dependencies on first run.

param(
    [switch]$Test,
    [switch]$Report,
    # Anything else goes straight to `python -m lsc`, so --dry-run, --write,
    # --rollback and --preset work from the launcher without this file having
    # to grow a switch for each one.
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

# -- find a usable interpreter to build the venv with -------------------------
#
# Not as simple as "run python". Windows ships a zero-byte python.exe stub in
# WindowsApps that opens the Microsoft Store instead of running anything, so
# every candidate has to be proven by actually executing it.
function Find-Python {
    $candidates = @(
        "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.13-64\python.exe",
        "$env:LOCALAPPDATA\Python\pythoncore-3.12-64\python.exe",
        "python3",
        "python",
        "py"
    )
    foreach ($candidate in $candidates) {
        try {
            $version = & $candidate --version 2>$null
            if ($LASTEXITCODE -eq 0 -and $version -match "Python 3\.(\d+)") {
                if ([int]$Matches[1] -ge 11) { return $candidate }
            }
        } catch {
            continue
        }
    }
    return $null
}

if (-not (Test-Path $venvPython)) {
    Write-Host "First run - setting up the virtual environment..." -ForegroundColor Cyan

    $python = Find-Python
    if (-not $python) {
        Write-Host ""
        Write-Host "No Python 3.11+ found." -ForegroundColor Red
        Write-Host "Install it from https://www.python.org/downloads/ and run this again."
        Write-Host "(The 'python' in WindowsApps is a Microsoft Store stub, not a real"
        Write-Host " interpreter - installing from python.org avoids it.)"
        exit 1
    }

    & $python -m venv .venv
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r requirements.txt
    Write-Host "Ready." -ForegroundColor Green
}

# Back to Continue before handing off. Under "Stop", Windows PowerShell treats
# anything a native program writes to stderr as a terminating error - and
# unittest writes its entire report there, so a passing test run would look
# like a crash.
$ErrorActionPreference = "Continue"

if ($Test) {
    & $venvPython -m unittest discover -s tests -v
} elseif ($Report) {
    & $venvPython -m lsc --report
} elseif ($Arguments) {
    & $venvPython -m lsc @Arguments
} else {
    & $venvPython -m lsc
}

# Pass the real exit code up, so a failing test run fails the caller too.
exit $LASTEXITCODE
