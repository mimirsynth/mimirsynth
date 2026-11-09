# CI (#360): install.ps1 run the documented way with options, `& ([scriptblock]::Create(...))`, against the stand-in docker of the
# installer-desktop job, up to the configuration it writes: a local install, and an existing Neo4j with TLS in Spanish.
$ErrorActionPreference = "Stop"
Write-Host "PowerShell $($PSVersionTable.PSVersion)"
$script = [scriptblock]::Create((Get-Content -Raw install.ps1))

function Read-Env([string]$Name) {
    $text = Get-Content -Raw (Join-Path $env:RUNNER_TEMP "$Name/.env")
    if ($text.Contains("`r")) { throw "$Name/.env has CRLF line endings" }
    return $text
}
function Assert-Line([string]$Text, [string]$Pattern) {
    if ($Text -notmatch "(?m)^$Pattern$") { throw "no line matches ^$Pattern$" }
}

& $script -Yes -From . -Version ci -NoStart -Dir (Join-Path $env:RUNNER_TEMP "ps-local")
$t = Read-Env "ps-local"
Assert-Line $t "COMPOSE_PROFILES=bundled"
Assert-Line $t "POSTGRES_PASSWORD=[0-9a-f]{64}"
Assert-Line $t "MIMIRSYNTH_VERSION=ci"

& $script -Yes -From . -Version ci -NoStart -Dir (Join-Path $env:RUNNER_TEMP "ps-neo4j") -Lang es `
    -Graph existing -GraphType neo4j -GraphHost localhost -GraphPort 1 -GraphTls -SkipGraphCheck
$t = Read-Env "ps-neo4j"
Assert-Line $t "MIMIRSYNTH_NEO4J_URI=bolt\+s://host\.docker\.internal:1"
Assert-Line $t "MIMIRSYNTH_DEFAULT_LANGUAGE=es"
Assert-Line $t "COMPOSE_PROFILES="

# #403: SemVer as update.sh compares it (the same cases), and what an existing installation is told about upgrading
$ast = [System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path install.ps1).Path, [ref]$null, [ref]$null)
foreach ($fn in @("Test-SemVer", "Compare-SemVer")) {
    $def = $ast.Find({ param($n) $n -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $n.Name -eq $fn }, $true)
    . ([scriptblock]::Create($def.Extent.Text))
}
$cases = 0
foreach ($line in Get-Content .github/semver-cases.txt) {
    if (-not $line.Trim() -or $line.StartsWith("#")) { continue }
    $l, $r, $want = -split $line
    $got = Compare-SemVer $l $r
    if ($got -ne [int]$want) { throw "Compare-SemVer $l $r = $got, expected $want" }
    if (-not (Test-SemVer $l)) { throw "$l should be a version" }
    $cases++
}
foreach ($v in @("latest", "ci", "0.15", "0.15.0.1", "01.2.3", "0.15.0-")) { if (Test-SemVer $v) { throw "$v should not be a version" } }
Write-Host "ok: $cases SemVer comparisons"

$dir = Join-Path $env:RUNNER_TEMP "ps-local"
$envFile = Join-Path $dir ".env"
[IO.File]::WriteAllText($envFile, ((Get-Content -Raw $envFile) -replace '(?m)^MIMIRSYNTH_VERSION=.*$', 'MIMIRSYNTH_VERSION=0.15.0-rc.1'))
$env:FAKE_CONTAINER = "0123456789ab"   # the stand-in docker now says that the application's container exists
function Get-Verdict([string]$To) { return (& $script -Yes -Lang en -Version $To -Dir $dir 6>&1 | Out-String) }
function Assert-Says([string]$Out, [string]$Text) { if (-not $Out.Contains($Text)) { Write-Host $Out; throw "the installer does not say: $Text" } }
$o = Get-Verdict "0.15.0"
Assert-Says $o "already installed"; Assert-Says $o "Version 0.15.0 is available (it is at 0.15.0-rc.1)."; Assert-Says $o "To upgrade it"
$o = Get-Verdict "0.14.0"
Assert-Says $o "0.14.0 is older than 0.15.0-rc.1, the version it is at"
if ($o.Contains("To upgrade it")) { throw "an older release is offered as an upgrade" }
$o = Get-Verdict "0.15.0-rc.1"
Assert-Says $o "It is at 0.15.0-rc.1 already: up to date."
if ((Get-Content -Raw $envFile) -notmatch '(?m)^MIMIRSYNTH_VERSION=0\.15\.0-rc\.1\r?$') { throw ".env was changed" }
Remove-Item Env:FAKE_CONTAINER
Write-Host "ok"
exit 0   # the stand-in docker's last answer (3, «not available») is still in $LASTEXITCODE, which the step would return
