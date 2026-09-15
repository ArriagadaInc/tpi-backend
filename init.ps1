# Harness TPI init (validator). Delegates to the portable Python implementation.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $python) { $python = Get-Command python3 -ErrorAction SilentlyContinue }
if ($null -eq $python) {
    Write-Error 'HARNESS INIT: FAIL - python no disponible. STOP - DO NOT MODIFY THE REPOSITORY - REQUEST HUMAN ASSISTANCE'
    exit 1
}
& $python.Source (Join-Path $root 'scripts/harness/init.py') @args
exit $LASTEXITCODE
