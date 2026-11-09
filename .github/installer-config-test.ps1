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
Write-Host "ok"
