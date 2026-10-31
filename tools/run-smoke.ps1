# Run smoke tests against a local build.
# Usage:  pwsh -File tools/run-smoke.ps1 [-Build dev|release] [-Test boot|race|all] [-Port 4370]
# Needs the dev build (debug server); the release build has no debug port.
param(
    [ValidateSet('dev', 'release')][string]$Build = 'dev',
    [ValidateSet('boot', 'race', 'all')][string]$Test = 'boot',
    [int]$Port = 4370
)

. D:\RecompDev\dev-env.ps1

$repo = Split-Path -Parent $PSScriptRoot
$exe = Get-ChildItem -LiteralPath (Join-Path $repo "build-$Build") -Filter 'Motor_Toon_Grand_Prix_Recompiled.exe' -ErrorAction SilentlyContinue |
    Select-Object -First 1
if (-not $exe) {
    Write-Error "no exe under build-$Build" -ErrorAction Continue
    exit 1
}

$tests = if ($Test -eq 'all') { @('boot', 'race') } else { @($Test) }
foreach ($t in $tests) {
    py -3 (Join-Path $repo "tests\smoke\${t}_smoke.py") --exe $exe.FullName --cue $env:MTGP_CUE --port $Port
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
exit 0
