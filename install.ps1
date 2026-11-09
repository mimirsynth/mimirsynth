<#
.SYNOPSIS
MimirSynth installer for Docker Desktop on Windows (and on macOS with PowerShell 7). On Linux, use install.sh.

.DESCRIPTION
  irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1 | iex
  With options:
  & ([scriptblock]::Create((irm https://github.com/MimirSynth/mimirsynth/releases/latest/download/install.ps1))) -Yes -Ollama

It checks Docker Desktop, asks a few questions, writes docker-compose.yml and .env (with generated secrets), starts the stack,
waits until it answers and opens the browser on the first-start wizard. Run it again at any time: it detects an existing install.
With -Yes it asks nothing and uses the parameters and the defaults. The password of an existing graph database is read from the
MIMIRSYNTH_GRAPH_PASSWORD environment variable, never from the command line.

.PARAMETER Graph
local: start the bundled FalkorDB (default). existing: use your FalkorDB or Neo4j server (-GraphType, -GraphHost, -GraphPort,
-GraphUser, -GraphDatabase, and -GraphTls for a Neo4j that asks for TLS, as Neo4j Aura does). Before anything starts it passes the
full connection test (address, credentials, version and write permission), or nothing is installed, unless -SkipGraphCheck.
#>
[CmdletBinding()]
param(
    [string]$Dir = "",
    [string]$Version = "",
    [int]$Port = 0,
    [ValidateSet("", "local", "existing")][string]$Graph = "",
    [ValidateSet("", "falkordb", "neo4j")][string]$GraphType = "",
    [string]$GraphHost = "",
    [int]$GraphPort = 0,
    [string]$GraphUser = "",
    [string]$GraphDatabase = "",
    [switch]$GraphTls,
    [switch]$SkipGraphCheck,
    [switch]$Ollama,
    [switch]$NoOllama,
    [switch]$NoStart,
    [switch]$NoBrowser,
    [ValidateSet("", "en", "es")][string]$Lang = "",
    [switch]$Yes,
    [string]$From = ""
)

# This file is plain ASCII on purpose: Windows PowerShell 5.1 reads scripts (and `irm | iex`) without a BOM in the ANSI code page.
# Spanish texts carry \uXXXX escapes, decoded at run time. A template must not contain any other backslash.
$SavedPrefs = @($ErrorActionPreference, $ProgressPreference)   # restored at the end: `irm | iex` runs in the caller's session
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is many times slower with the progress bar in Windows PowerShell
$Repo = "MimirSynth/mimirsynth"
$EmbedModel = "nomic-embed-text"
$WaitSeconds = 300
$OnMac = (Get-Variable IsMacOS -ErrorAction SilentlyContinue) -and $IsMacOS
$OnLinux = (Get-Variable IsLinux -ErrorAction SilentlyContinue) -and $IsLinux
if ($OnLinux) { Write-Error "On Linux, use install.sh."; return }
try { [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12 } catch { }

if (-not $Lang) { if ((Get-UICulture).TwoLetterISOLanguageName -eq "es" -or (Get-Culture).TwoLetterISOLanguageName -eq "es") { $Lang = "es" } else { $Lang = "en" } }
$Interactive = (-not $Yes) -and [Environment]::UserInteractive -and -not [Console]::IsInputRedirected
# Shared state. A hashtable, not $script: variables: run as `& ([scriptblock]::Create(...))` the parameters live in another scope.
$St = @{ Version = $Version; Port = $Port; Graph = $Graph; GraphType = $GraphType; GraphHost = $GraphHost; GraphPort = $GraphPort;
         GraphUser = $GraphUser; GraphDatabase = $GraphDatabase; GraphPassword = [string]$env:MIMIRSYNTH_GRAPH_PASSWORD;
         GraphTls = $(if ($GraphTls) { "1" } else { "" }); ContainerHost = ""; UseOllama = $false;
         EnvLines = @(); HealthBody = ""; SetupCode = ""; GraphTestAnswer = ""; Probed = $false; Wrote = $false; Removed = $false }

function T([string]$En, [string]$Es, [object[]]$Fmt = @()) {
    $s = if ($Lang -eq "es") { [regex]::Unescape($Es) } else { $En }
    if ($Fmt.Count) { $s = $s -f $Fmt }
    return $s
}
function Say([string]$En, [string]$Es, [object[]]$Fmt = @()) { Write-Host (T $En $Es $Fmt) }
function Step([string]$En, [string]$Es) { Write-Host ""; Write-Host ("== " + (T $En $Es)) -ForegroundColor Cyan }
function Warn([string]$En, [string]$Es, [object[]]$Fmt = @()) { Write-Host ("WARN: " + (T $En $Es $Fmt)) -ForegroundColor Yellow }
function Fail([string]$En, [string]$Es, [object[]]$Fmt = @()) { throw ("ERROR: " + (T $En $Es $Fmt)) }
function Ask([string]$En, [string]$Es, [string]$Default) {
    if (-not $Interactive) { return $Default }
    $q = T $En $Es
    if ($Default) { $q = "$q [$Default]" }
    $a = Read-Host $q
    if ($a) { return $a.Trim() } else { return $Default }
}
function AskSecret([string]$En, [string]$Es) {
    if (-not $Interactive) { return "" }
    $s = Read-Host (T $En $Es) -AsSecureString
    $p = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($s)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($p) } finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($p) }
}
function YesNo([string]$En, [string]$Es, [bool]$Default) {
    if (-not $Interactive) { return $Default }
    $h = if ($Default) { if ($Lang -eq "es") { "S/n" } else { "Y/n" } } else { if ($Lang -eq "es") { "s/N" } else { "y/N" } }
    $a = Read-Host ("{0} [{1}]" -f (T $En $Es), $h)
    if (-not $a) { return $Default }
    return $a.Trim() -match '^(y|yes|s|si|s\u00ed)$'
}

# Native commands: Windows PowerShell 5.1 turns their stderr into errors when $ErrorActionPreference is Stop, so they run with Continue.
function Invoke-Native([string]$Exe, [string[]]$ArgList, [switch]$Quiet) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { if ($Quiet) { & $Exe @ArgList *> $null } else { & $Exe @ArgList | Out-Host } } catch { return 1 } finally { $ErrorActionPreference = $old }
    return $LASTEXITCODE
}
function Get-NativeOutput([string]$Exe, [string[]]$ArgList) {
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    try { return @(& $Exe @ArgList 2>$null) } catch { return @() } finally { $ErrorActionPreference = $old }
}
function Dc([string[]]$ArgList, [switch]$Quiet) { return Invoke-Native "docker" (@("compose") + $ArgList) -Quiet:$Quiet }

function New-Secret {
    $b = New-Object byte[] 32
    $r = [Security.Cryptography.RandomNumberGenerator]::Create(); $r.GetBytes($b); $r.Dispose()
    return -join ($b | ForEach-Object { $_.ToString("x2") })
}
function Test-Tcp([string]$HostName, [int]$PortNumber, [int]$Ms = 5000) {
    $c = New-Object Net.Sockets.TcpClient
    try { $t = $c.ConnectAsync($HostName, $PortNumber); return ($t.Wait($Ms) -and $c.Connected) } catch { return $false } finally { $c.Close() }
}
function Get-Http([string]$Url, [string]$Method = "GET", [string]$Body = "", [hashtable]$Headers = @{}, [int]$Timeout = 5) {
    # -> @{ Code; Body }; Code 0 when nothing answers
    $p = @{ Uri = $Url; Method = $Method; UseBasicParsing = $true; TimeoutSec = $Timeout; Headers = $Headers }
    if ($Body) { $p.Body = [Text.Encoding]::UTF8.GetBytes($Body); $p.ContentType = "application/json" }
    try { $r = Invoke-WebRequest @p; return @{ Code = [int]$r.StatusCode; Body = [string]$r.Content } }
    catch {
        $code = 0
        if ($_.Exception.Response) { try { $code = [int]$_.Exception.Response.StatusCode } catch { } }
        $msg = ""; if ($_.ErrorDetails) { $msg = [string]$_.ErrorDetails.Message }
        return @{ Code = $code; Body = $msg }
    }
}
function Get-EnvValue([string]$Key) {
    $line = Get-Content -LiteralPath (Join-Path $Dir ".env") -Encoding UTF8 | Where-Object { $_ -match "^$Key=" } | Select-Object -Last 1
    if (-not $line) { return "" }
    return ($line.Substring($Key.Length + 1)).Trim('"', "'")
}
function Format-EnvValue([string]$V) {
    # a value as Docker Compose reads it literally from .env
    if ($V -notmatch '[^A-Za-z0-9._@:/+=,-]') { return $V }
    if ($V -notmatch "'") { return "'" + $V + "'" }
    return '"' + ($V.Replace('\', '\\').Replace('"', '\"').Replace('$', '$$')) + '"'
}
function Set-EnvValue([string]$Key, [string]$Value) {
    $done = $false
    for ($i = 0; $i -lt $St.EnvLines.Count; $i++) {
        if ($St.EnvLines[$i] -match "^(# ?)?$Key=") { $St.EnvLines[$i] = "$Key=$Value"; $done = $true; break }
    }
    if (-not $done) { $St.EnvLines += "$Key=$Value" }
}
function Save-Utf8([string]$Path, [string]$Text) { [IO.File]::WriteAllText($Path, $Text, (New-Object Text.UTF8Encoding $false)) }

function Get-ReleaseFile([string]$Name, [string]$Dest) {
    if ($From) {
        $src = Join-Path $From $Name
        if (-not (Test-Path -LiteralPath $src) -and $Name -eq "env.example") { $src = Join-Path $From ".env.example" }
        # LF line endings, as in the release (a Windows checkout may have CRLF)
        Save-Utf8 $Dest (([IO.File]::ReadAllText($src)) -replace "`r`n", "`n")
        return
    }
    $url = if ($St.Version -and $St.Version -ne "latest") { "https://github.com/$Repo/releases/download/v$($St.Version)/$Name" } else { "https://github.com/$Repo/releases/latest/download/$Name" }
    Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $Dest -TimeoutSec 120
}

# Versions compare as SemVer 2.0, as in update.sh (#403): 0.15.0 > 0.15.0-rc.2 > 0.15.0-rc.1 > 0.14.0, a pre-release below its final
# release. Names such as "latest" or "ci" are not versions: nothing is compared with them.
function Test-SemVer([string]$V) {
    return $V -cmatch '^v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(-[0-9A-Za-z-]+(\.[0-9A-Za-z-]+)*)?(\+[0-9A-Za-z.-]+)?$'
}
function Compare-SemVer([string]$Left, [string]$Right) {
    # -1, 0 or 1 when $Left is older than, the same as or newer than $Right (both versions); what follows "+" does not count
    $l = ($Left -replace '^v', '') -replace '\+.*$', ''; $r = ($Right -replace '^v', '') -replace '\+.*$', ''
    $il = $l.IndexOf('-'); $ir = $r.IndexOf('-')
    $cl = $(if ($il -ge 0) { $l.Substring(0, $il) } else { $l }).Split('.'); $cr = $(if ($ir -ge 0) { $r.Substring(0, $ir) } else { $r }).Split('.')
    for ($i = 0; $i -lt 3; $i++) {
        $x = [decimal]$cl[$i]; $y = [decimal]$cr[$i]
        if ($x -gt $y) { return 1 } elseif ($x -lt $y) { return -1 }
    }
    if ($il -lt 0) { if ($ir -lt 0) { return 0 } else { return 1 } }
    if ($ir -lt 0) { return -1 }
    $pl = $l.Substring($il + 1).Split('.'); $pr = $r.Substring($ir + 1).Split('.')
    for ($i = 0; $i -lt [Math]::Min($pl.Count, $pr.Count); $i++) {
        # identifier by identifier: numbers as numbers and below words, words in ASCII order
        $x = $pl[$i]; $y = $pr[$i]
        if ($x -ceq $y) { continue }
        $nx = $x -match '^[0-9]+$'; $ny = $y -match '^[0-9]+$'
        if ($nx -and $ny) { if ([decimal]$x -gt [decimal]$y) { return 1 } else { return -1 } }
        if ($nx) { return -1 }
        if ($ny) { return 1 }
        if ([string]::CompareOrdinal($x, $y) -gt 0) { return 1 } else { return -1 }
    }
    if ($pl.Count -gt $pr.Count) { return 1 } elseif ($pl.Count -lt $pr.Count) { return -1 } else { return 0 }
}
function Show-UpgradeVerdict {
    # An existing installation against the release an upgrade would go to (-Version, or the latest stable one): $true when there is
    # one to go to or it is not known. Like update.sh, it never offers to go down to the latest stable release (#403).
    $cur = Get-EnvValue "MIMIRSYNTH_VERSION"
    if (-not (Test-SemVer $cur)) { return $true }
    $to = $St.Version
    if (-not $to) { try { $to = [string](Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 15).tag_name } catch { $to = "" } }
    if (-not (Test-SemVer $to)) { return $true }
    $cur = $cur -replace '^v', ''; $to = $to -replace '^v', ''
    $c = Compare-SemVer $to $cur
    if ($c -gt 0) {
        Say "Version {1} is available (it is at {0})." "Est\u00e1 disponible la versi\u00f3n {1} (ahora est\u00e1 en la {0})." @($cur, $to)
        return $true
    }
    if ($c -eq 0) { Say "It is at {0} already: up to date." "Ya est\u00e1 en la {0}: est\u00e1 al d\u00eda." @($cur) }
    elseif ($St.Version) {
        Say "{1} is older than {0}, the version it is at: ./update.sh --version {1} goes down only if that version knows the database (see Upgrading in docs/INSTALL.md)." `
            "{1} es anterior a {0}, la versi\u00f3n en la que est\u00e1: ./update.sh --version {1} solo baja si esa versi\u00f3n conoce la base de datos (ver Actualizar en docs/es/INSTALL.md)." @($cur, $to)
    }
    else {
        Say "It is at {0}, newer than the latest stable release ({1}): there is nothing to upgrade to." `
            "Est\u00e1 en la {0}, m\u00e1s reciente que la \u00faltima versi\u00f3n estable ({1}): no hay nada a lo que actualizar." @($cur, $to)
    }
    return $false
}

# ---- Docker Desktop and Compose v2 ----
function Test-Docker {
    Step "Docker" "Docker"
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        if ($OnMac) {
            Fail "Docker is not installed. Install Docker Desktop (https://docs.docker.com/desktop/setup/install/mac-install/), start it and run this installer again." `
                 "Docker no est\u00e1 instalado. Instala Docker Desktop (https://docs.docker.com/desktop/setup/install/mac-install/), \u00e1brelo y vuelve a ejecutar este instalador."
        }
        Say "Docker Desktop is not installed. It needs WSL2: in a PowerShell opened as administrator run 'wsl --install' and restart if asked." `
            "Docker Desktop no est\u00e1 instalado. Necesita WSL2: en un PowerShell abierto como administrador ejecuta 'wsl --install' y reinicia si te lo pide."
        Fail "Then install Docker Desktop (https://docs.docker.com/desktop/setup/install/windows-install/, or 'winget install Docker.DockerDesktop'), start it and run this installer again." `
             "Despu\u00e9s instala Docker Desktop (https://docs.docker.com/desktop/setup/install/windows-install/, o 'winget install Docker.DockerDesktop'), \u00e1brelo y vuelve a ejecutar este instalador."
    }
    if ((Invoke-Native "docker" @("info") -Quiet) -ne 0) {
        Say "Docker Desktop is not running: starting it..." "Docker Desktop no est\u00e1 en marcha: arranc\u00e1ndolo..."
        if ($OnMac) { Invoke-Native "open" @("-a", "Docker") -Quiet | Out-Null }
        else {
            $exe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
            if (Test-Path -LiteralPath $exe) { Start-Process -FilePath $exe | Out-Null }
        }
        $t0 = Get-Date
        while ((Invoke-Native "docker" @("info") -Quiet) -ne 0) {
            if (((Get-Date) - $t0).TotalSeconds -gt 180) {
                Fail "Docker Desktop did not start: open it, wait until it says it is running and run this installer again. On Windows it needs WSL2 ('wsl --status')." `
                     "Docker Desktop no ha arrancado: \u00e1brelo, espera a que diga que est\u00e1 en marcha y vuelve a ejecutar este instalador. En Windows necesita WSL2 ('wsl --status')."
            }
            Start-Sleep -Seconds 3
        }
    }
    if ((Invoke-Native "docker" @("compose", "version") -Quiet) -ne 0) { Fail "Docker Compose v2 is missing: update Docker Desktop." "Falta Docker Compose v2: actualiza Docker Desktop." }
    $v = (Get-NativeOutput "docker" @("compose", "version", "--short")) -join ""
    Write-Host ("{0} | Compose {1}" -f ((Get-NativeOutput "docker" @("--version")) -join ""), $v)
}

# ---- questions ----
function Clear-GraphValues {
    $St.GraphType = ""; $St.GraphHost = ""; $St.GraphPort = 0; $St.GraphUser = ""; $St.GraphPassword = ""; $St.GraphDatabase = ""; $St.GraphTls = ""
}
function Read-GraphChoice {
    Step "Graph database" "Base de datos de grafos"
    if (-not $St.Graph) {
        Say "  1) local: a FalkorDB started next to MimirSynth (recommended if you are starting)" "  1) local: un FalkorDB que se arranca junto a MimirSynth (recomendado si empiezas)"
        Say "  2) existing: a FalkorDB or Neo4j server you already run" "  2) existente: un servidor FalkorDB o Neo4j que ya tienes"
        $a = Ask "Choose" "Elige" "1"
        $St.Graph = if ($a -match '^(2|e|existing|existente)$') { "existing" } else { "local" }
    }
    if ($St.Graph -ne "existing") { return }
    while ($true) {
        if (-not $St.GraphType) { $St.GraphType = Ask "Type: falkordb or neo4j" "Tipo: falkordb o neo4j" "falkordb" }
        if ($St.GraphType -notin @("falkordb", "neo4j")) {
            if (-not $Interactive) { Fail "-GraphType must be falkordb or neo4j" "-GraphType debe ser falkordb o neo4j" }
            $St.GraphType = ""; continue
        }
        if (-not $St.GraphHost) { $St.GraphHost = Ask "Host (name or IP address)" "Host (nombre o direcci\u00f3n IP)" "" }
        if (-not $St.GraphHost) {
            if (-not $Interactive) { Fail "-GraphHost is required with -Graph existing" "-GraphHost es obligatorio con -Graph existing" }
            continue
        }
        $dport = if ($St.GraphType -eq "neo4j") { "7687" } else { "6379" }
        if (-not $St.GraphPort) {
            $p = Ask "Port" "Puerto" $dport
            if ($p -notmatch '^\d+$') { continue }
            $St.GraphPort = [int]$p
        }
        if ($Interactive -and -not $St.GraphUser) {
            $St.GraphUser = if ($St.GraphType -eq "neo4j") { Ask "User" "Usuario" "neo4j" } else { Ask "User (empty if it has none)" "Usuario (vac\u00edo si no tiene)" "" }
        }
        if ($St.GraphType -eq "neo4j" -and -not $St.GraphUser) { $St.GraphUser = "neo4j" }
        if ($Interactive -and -not $St.GraphPassword) { $St.GraphPassword = AskSecret "Password (empty if it has none)" "Contrase\u00f1a (vac\u00eda si no tiene)" }
        if ($St.GraphType -eq "neo4j" -and $Interactive -and -not $St.GraphDatabase) {
            $St.GraphDatabase = Ask "Database (empty: the server's default)" "Base de datos (vac\u00edo: la predeterminada del servidor)" ""
        }
        if ($St.GraphType -eq "neo4j" -and -not $St.GraphTls) {
            $St.GraphTls = if (YesNo "Does it ask for TLS (bolt+s, as Neo4j Aura does)?" "\u00bfPide TLS (bolt+s, como Neo4j Aura)?" $false) { "1" } else { "0" }
        }
        # The environment has no TLS setting for FalkorDB: that connection is saved in Administration > Graph database instead.
        if ($St.GraphType -eq "falkordb" -and $St.GraphTls -eq "1") {
            Fail "a FalkorDB with TLS is configured in Administration > Graph database: install with -Graph local and change it there" `
                 "un FalkorDB con TLS se configura en Administraci\u00f3n > Base de datos de grafos: instala con -Graph local y c\u00e1mbialo all\u00ed"
        }
        Say "Checking that {0}:{1} answers..." "Comprobando que {0}:{1} responde..." @($St.GraphHost, $St.GraphPort)
        if (Test-Tcp $St.GraphHost $St.GraphPort) { Say "It answers." "Responde."; break }
        Warn "nothing answers at {0}:{1}" "nada responde en {0}:{1}" @($St.GraphHost, $St.GraphPort)
        if ($SkipGraphCheck) { break }
        if (-not $Interactive) { Fail "check the address, or add -SkipGraphCheck" "revisa la direcci\u00f3n, o a\u00f1ade -SkipGraphCheck" }
        if (YesNo "Enter the values again?" "\u00bfVolver a introducir los datos?" $true) {
            Clear-GraphValues
            continue
        }
        if (-not (YesNo "Continue anyway?" "\u00bfContinuar de todos modos?" $false)) { Fail "cancelled" "cancelado" }
        break
    }
    # Inside the container, localhost is the container itself; Docker Desktop resolves host.docker.internal to this computer.
    $St.ContainerHost = $St.GraphHost
    if ($St.GraphHost -in @("localhost", "127.0.0.1", "::1")) {
        $St.ContainerHost = "host.docker.internal"
        Say "MimirSynth will reach it as host.docker.internal." "MimirSynth llegar\u00e1 a \u00e9l como host.docker.internal."
    }
}

function Read-OllamaChoice {
    Step "Embeddings" "Embeddings"
    $hostOllama = (Get-Http "http://127.0.0.1:11434/api/tags" -Timeout 2).Code -eq 200
    if ($Ollama) { $St.UseOllama = $true }
    elseif ($NoOllama) { $St.UseOllama = $false }
    elseif ($hostOllama) {
        Say "Ollama is already running on this computer: MimirSynth will use it (http://host.docker.internal:11434/v1)." `
            "Ollama ya est\u00e1 en marcha en este ordenador: MimirSynth lo usar\u00e1 (http://host.docker.internal:11434/v1)."
        $St.UseOllama = YesNo "Start a bundled Ollama anyway?" "\u00bfArrancar de todos modos un Ollama incluido?" $false
    }
    else {
        Say "MimirSynth needs an embedding model to search its memory. A bundled Ollama runs it on this computer's CPU (the image is a download of about 3.5 GB, the model about 300 MB). Without it, configure a provider in the setup wizard." `
            "MimirSynth necesita un modelo de embeddings para buscar en su memoria. Un Ollama incluido lo ejecuta en la CPU de este ordenador (la imagen es una descarga de unos 3,5 GB, el modelo unos 300 MB). Sin \u00e9l, configura un proveedor en el asistente."
        $St.UseOllama = $Interactive -and (YesNo "Start a bundled Ollama?" "\u00bfArrancar un Ollama incluido?" $true)
    }
    if (-not $St.UseOllama -and $hostOllama) {
        $tags = (Get-Http "http://127.0.0.1:11434/api/tags" -Timeout 2).Body
        if ($tags -notmatch [regex]::Escape("`"$EmbedModel")) {
            Warn "the Ollama on this computer does not have {0}: run 'ollama pull {0}'" "el Ollama de este ordenador no tiene {0}: ejecuta 'ollama pull {0}'" @($EmbedModel)
        }
    }
}

function Select-Port {
    if ($St.Port) {
        if (Test-Tcp "127.0.0.1" $St.Port 1000) { Fail "port {0} is in use: choose another with -Port" "el puerto {0} est\u00e1 en uso: elige otro con -Port" @($St.Port) }
        return
    }
    $St.Port = 8000
    while (Test-Tcp "127.0.0.1" $St.Port 1000) {
        $St.Port++
        if ($St.Port -ge 8100) { Fail "no free port between 8000 and 8099: use -Port" "no hay ning\u00fan puerto libre entre 8000 y 8099: usa -Port" }
    }
    if ($St.Port -ne 8000) { Say "Port 8000 is in use: MimirSynth will use {0}." "El puerto 8000 est\u00e1 en uso: MimirSynth usar\u00e1 el {0}." @($St.Port) }
}

function Write-Config {
    Step "Configuration" "Configuraci\u00f3n"
    if (-not $St.Version) {
        if ($From) { $St.Version = "latest" }
        else {
            try { $St.Version = [string](Invoke-RestMethod -UseBasicParsing -Uri "https://api.github.com/repos/$Repo/releases/latest" -TimeoutSec 15).tag_name } catch { $St.Version = "" }
            if (-not $St.Version) { $St.Version = "latest" }
        }
    }
    $St.Version = $St.Version.TrimStart("v")
    $compose = Join-Path $Dir "docker-compose.yml"; $envFile = Join-Path $Dir ".env"
    $St.Wrote = $true
    Get-ReleaseFile "docker-compose.yml" $compose
    Get-ReleaseFile "env.example" $envFile
    Get-ReleaseFile "update.sh" (Join-Path $Dir "update.sh")
    $profiles = @()
    if ($St.Graph -eq "local") { $profiles += "bundled" }
    if ($St.UseOllama) {
        if (Select-String -LiteralPath $compose -Pattern '^  ollama:' -Quiet) { $profiles += "ollama" }
        else { Warn "version {0} has no bundled Ollama: configure embeddings in the setup wizard" "la versi\u00f3n {0} no incluye Ollama: configura los embeddings en el asistente" @($St.Version); $St.UseOllama = $false }
    }
    $St.EnvLines = @(([IO.File]::ReadAllText($envFile)) -replace "`r", "" -split "`n")
    if ($St.EnvLines.Count -and $St.EnvLines[-1] -eq "") { $St.EnvLines = $St.EnvLines[0..($St.EnvLines.Count - 2)] }
    Set-EnvValue "POSTGRES_PASSWORD" (New-Secret)
    Set-EnvValue "MIMIRSYNTH_SESSION_SECRET" (New-Secret)
    Set-EnvValue "MIMIRSYNTH_VERSION" $St.Version
    Set-EnvValue "MIMIRSYNTH_PORT" ([string]$St.Port)
    Set-EnvValue "MIMIRSYNTH_DEFAULT_LANGUAGE" $Lang
    Set-EnvValue "COMPOSE_PROFILES" ($profiles -join ",")
    if ($St.UseOllama) { Set-EnvValue "MIMIRSYNTH_EMBEDDING_BASE_URL" "http://ollama:11434/v1" }
    Set-GraphEnv
    Save-EnvFile
    if ((Dc @("config", "-q") -Quiet) -ne 0) { Fail "the generated configuration is not valid (docker compose config)" "la configuraci\u00f3n generada no es v\u00e1lida (docker compose config)" }
    $pn = if ($profiles.Count) { $profiles -join "," } else { T "none" "ninguno" }
    Say "Version {0} | port {1} | profiles: {2} | secrets generated in {3}" "Versi\u00f3n {0} | puerto {1} | perfiles: {2} | secretos generados en {3}" @($St.Version, $St.Port, $pn, $envFile)
}

# ---- an existing graph database ----
function Save-EnvFile {
    $envFile = Join-Path $Dir ".env"
    Save-Utf8 $envFile (($St.EnvLines -join "`n") + "`n")
    if ($OnMac) { Invoke-Native "chmod" @("600", $envFile) -Quiet | Out-Null }
}
# The environment wins over Administration > Graph database when it is set (#358): an existing database the installer was told about
# goes in .env, read-only in the interface. A local install writes none of these, so the interface can change it.
function Set-GraphEnv {
    $keys = @("MIMIRSYNTH_GRAPH_BACKEND", "MIMIRSYNTH_FALKOR_HOST", "MIMIRSYNTH_FALKOR_PORT", "MIMIRSYNTH_FALKOR_USERNAME", "MIMIRSYNTH_FALKOR_PASSWORD",
              "MIMIRSYNTH_NEO4J_URI", "MIMIRSYNTH_NEO4J_USER", "MIMIRSYNTH_NEO4J_PASSWORD", "MIMIRSYNTH_NEO4J_DATABASE")
    for ($i = 0; $i -lt $St.EnvLines.Count; $i++) {   # back to the commented examples, without the values
        foreach ($k in $keys) { if ($St.EnvLines[$i] -match "^$k=") { $St.EnvLines[$i] = "# $k=" } }
    }
    if ($St.Graph -ne "existing") { return }
    Set-EnvValue "MIMIRSYNTH_GRAPH_BACKEND" $St.GraphType
    if ($St.GraphType -eq "falkordb") {
        Set-EnvValue "MIMIRSYNTH_FALKOR_HOST" (Format-EnvValue $St.ContainerHost)
        Set-EnvValue "MIMIRSYNTH_FALKOR_PORT" ([string]$St.GraphPort)
        if ($St.GraphUser) { Set-EnvValue "MIMIRSYNTH_FALKOR_USERNAME" (Format-EnvValue $St.GraphUser) }
        if ($St.GraphPassword) { Set-EnvValue "MIMIRSYNTH_FALKOR_PASSWORD" (Format-EnvValue $St.GraphPassword) }
    }
    else {
        $scheme = if ($St.GraphTls -eq "1") { "bolt+s" } else { "bolt" }
        Set-EnvValue "MIMIRSYNTH_NEO4J_URI" (Format-EnvValue ("{0}://{1}:{2}" -f $scheme, $St.ContainerHost, $St.GraphPort))
        Set-EnvValue "MIMIRSYNTH_NEO4J_USER" (Format-EnvValue $St.GraphUser)
        if ($St.GraphPassword) { Set-EnvValue "MIMIRSYNTH_NEO4J_PASSWORD" (Format-EnvValue $St.GraphPassword) }
        if ($St.GraphDatabase) { Set-EnvValue "MIMIRSYNTH_NEO4J_DATABASE" (Format-EnvValue $St.GraphDatabase) }
    }
}

# The full test, before anything starts: graphconn.probe, the same steps as POST /api/admin/graph/test (address, TLS, credentials,
# version, write permission and what the database holds), in a throwaway container of the release's own image (plain `docker run`,
# so it creates no volume or network of the project), which reaches the server as MimirSynth will. The connection goes in on stdin
# (base64 JSON, the endpoint's body), never on a command line. Exit status 3: a release without graphconn (before #358); 4: the test
# itself could not run. The same text as PROBE_PY in install.sh (CI compares them).
$ProbePy = "import base64,json,os,sys,importlib.util as u;sys.excepthook=lambda t,v,b:(print(repr(v)),sys.stdout.flush(),os._exit(4));u.find_spec('mimirsynth.graphconn') or sys.exit(3);from mimirsynth.graphconn import probe;from mimirsynth.graphdb import Connection;b=json.loads(base64.b64decode(sys.stdin.buffer.read()));r=probe(Connection(b['backend'],b['host'],int(b.get('port') or 0),b.get('user') or '',b.get('password') or '',bool(b.get('tls')),b.get('database') or ''),sys.argv[1]);s=r['server'] or {};print(' '.join(str(x) for x in (s.get('server'),s.get('version')) if x)+'|'+str(len(r['graphs'])) if r['ok'] else r['error']['message']);sys.exit(0 if r['ok'] else 1)"
function Invoke-GraphProbe {
    # -> 0 passed (GraphTestAnswer: "server version|graphs"), 1 failed (GraphTestAnswer: the cause, in the user's language), 3 not available
    $body = @{ backend = $St.GraphType; host = $St.ContainerHost; port = [int]$St.GraphPort; user = [string]$St.GraphUser;
               password = [string]$St.GraphPassword; tls = ($St.GraphTls -eq "1"); database = [string]$St.GraphDatabase } | ConvertTo-Json -Compress
    $b64 = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($body))
    $img = (Get-NativeOutput "docker" @("compose", "config", "--images", "mimirsynth") | Where-Object { $_ -match "/mimirsynth:" } | Select-Object -First 1)   # it lists postgres too, in no fixed order
    if (-not $img) { $img = "ghcr.io/mimirsynth/mimirsynth:$($St.Version)" }
    $old = $ErrorActionPreference; $ErrorActionPreference = "Continue"; $enc = $null
    try {
        try { $enc = [Console]::OutputEncoding; [Console]::OutputEncoding = New-Object Text.UTF8Encoding $false } catch { $enc = $null }
        # (the pipe may put a byte order mark before the text: the test reads bytes and base64 skips it)
        $out = @($b64 | & docker run --rm -i --add-host "host.docker.internal:host-gateway" --read-only --tmpfs /tmp --cap-drop ALL `
                     --security-opt no-new-privileges $img python -c $ProbePy $Lang)
        $rc = $LASTEXITCODE
    }
    catch { $out = @(); $rc = -1 }
    finally {
        if ($enc) { try { [Console]::OutputEncoding = $enc } catch { } }
        $ErrorActionPreference = $old
    }
    $St.GraphTestAnswer = if ($out.Count) { [string]$out[-1] } else { "" }
    if ($rc -in @(0, 1, 3)) { return $rc }
    Warn "could not run the connection test in a container (exit status {0}): {1}" "no se ha podido ejecutar la prueba de conexi\u00f3n en un contenedor (c\u00f3digo {0}): {1}" @($rc, $St.GraphTestAnswer)
    return 3
}

function Remove-Written {
    # removes what this run wrote, so that running the installer again starts from the questions
    if (-not $St.Wrote) { return }
    foreach ($f in @("docker-compose.yml", ".env", "update.sh")) { Remove-Item -LiteralPath (Join-Path $Dir $f) -Force -ErrorAction SilentlyContinue }
    $St.Removed = $true
}

function Test-GraphBeforeStart {
    Step "Graph database: connection test" "Base de datos de grafos: prueba de conexi\u00f3n"
    while ($true) {
        Say "Testing {0} at {1}:{2} from a MimirSynth container: credentials, version and write permission (the first time, the image is downloaded)..." `
            "Probando {0} en {1}:{2} desde un contenedor de MimirSynth: credenciales, versi\u00f3n y permiso de escritura (la primera vez se descarga la imagen)..." @($St.GraphType, $St.ContainerHost, $St.GraphPort)
        $rc = Invoke-GraphProbe
        if ($rc -eq 0) {
            $St.Probed = $true
            $parts = $St.GraphTestAnswer.Split("|")
            Say "Connection test passed: {0}, {1} graph(s) or partition(s) found." "La prueba de conexi\u00f3n ha pasado: {0}, {1} grafo(s) o partici\u00f3n(es) encontrados." @($parts[0], $parts[-1])
            return
        }
        if ($rc -eq 3) {
            Say "This release cannot test it before the start: it is tested once MimirSynth answers." "Esta versi\u00f3n no puede probarla antes del arranque: se prueba cuando MimirSynth responda."
            return
        }
        Warn "the connection test failed: {0}" "la prueba de conexi\u00f3n ha fallado: {0}" @($St.GraphTestAnswer)
        if ($SkipGraphCheck) { return }
        if ($Interactive) {
            if (YesNo "Enter the values again?" "\u00bfVolver a introducir los datos?" $true) {
                Clear-GraphValues
                Read-GraphChoice; Set-GraphEnv; Save-EnvFile
                continue
            }
            if (YesNo "Install anyway?" "\u00bfInstalar de todos modos?" $false) { return }
        }
        Remove-Written
        Fail "the graph database does not pass the connection test, so nothing was installed: fix the cause, or add -SkipGraphCheck" `
             "la base de datos de grafos no pasa la prueba de conexi\u00f3n, as\u00ed que no se ha instalado nada: corrige la causa, o a\u00f1ade -SkipGraphCheck"
    }
}

# ---- after the start ----
function Wait-Health {
    # -> 0 healthy; 2 it answers, but something it needs does not; 1 no answer
    $t0 = Get-Date; $first503 = $null; $St.HealthBody = ""
    while (((Get-Date) - $t0).TotalSeconds -lt $WaitSeconds) {
        $r = Get-Http "http://127.0.0.1:$($St.Port)/api/health"
        $St.HealthBody = $r.Body
        if ($r.Code -eq 200) { return 0 }
        if ($r.Code -eq 503) {
            if (-not $first503) { $first503 = Get-Date }
            if (((Get-Date) - $first503).TotalSeconds -ge 60) { return 2 }
        }
        Start-Sleep -Seconds 3
    }
    if ($first503) { return 2 }
    return 1
}

function Get-SetupCode {
    # the first-start code from the log (the last one, if the container restarted)
    $code = ""; $after = $false
    foreach ($l in (Get-NativeOutput "docker" @("compose", "logs", "--no-log-prefix", "mimirsynth"))) {
        if ($l -match "FIRST START") { $after = $true; continue }
        if ($after -and $l -match '^\s+([A-Za-z0-9_-]+)\s*$') { $code = $Matches[1]; $after = $false }
    }
    return $code
}

# The same full test through the API (#358), of the connection in force (no body: the one in .env, with its password), for when it
# did not run before the start. While there is no administrator the endpoint takes the first-start code as X-Setup-Code. It answers
# 200 with "ok" true or false and, when false, the cause in "error.message"; a release without it answers 404. Returns 0 ok, 1 failed
# (GraphTestAnswer has the cause), 3 not available.
function Test-GraphViaApi {
    $r = Get-Http "http://127.0.0.1:$($St.Port)/api/admin/graph/test" -Method POST -Headers @{ "X-Setup-Code" = $St.SetupCode; "Accept-Language" = $Lang } -Timeout 30
    $St.GraphTestAnswer = if ($r.Body.Length -gt 300) { $r.Body.Substring(0, 300) } else { $r.Body }
    if ($r.Code -in @(0, 401, 403, 404, 405)) { return 3 }
    if ($r.Code -ge 200 -and $r.Code -lt 300) {
        try { $j = $r.Body | ConvertFrom-Json } catch { return 1 }
        if ($j.ok) { return 0 }
        if ($j.error -and $j.error.message) { $St.GraphTestAnswer = [string]$j.error.message }
    }
    return 1
}

function Test-GraphFromContainer {
    Step "Graph database" "Base de datos de grafos"
    $py = "import socket, sys; socket.create_connection((sys.argv[1], int(sys.argv[2])), 5)"
    if ((Dc @("exec", "-T", "mimirsynth", "python", "-c", $py, $St.ContainerHost, [string]$St.GraphPort) -Quiet) -eq 0) {
        Say "The container reaches {0}:{1}." "El contenedor llega a {0}:{1}." @($St.ContainerHost, $St.GraphPort)
    }
    else {
        Warn "the container does not reach {0}:{1}: check the address, the server's listen address and the firewall, then change .env and run 'docker compose up -d'" `
             "el contenedor no llega a {0}:{1}: revisa la direcci\u00f3n, la direcci\u00f3n en la que escucha el servidor y el cortafuegos, cambia .env y ejecuta 'docker compose up -d'" @($St.ContainerHost, $St.GraphPort)
    }
    switch (Test-GraphViaApi) {
        0 { Say "Connection test passed." "La prueba de conexi\u00f3n ha pasado." }
        1 { Warn "the connection test failed: {0}" "la prueba de conexi\u00f3n ha fallado: {0}" @($St.GraphTestAnswer) }
        default { Say "The full connection test (credentials, version, permissions) runs in the setup wizard." "La prueba completa de conexi\u00f3n (credenciales, versi\u00f3n, permisos) se hace en el asistente." }
    }
}

# =================================================================================================================================
$failed = $false
Push-Location
try {
    Say "MimirSynth installer" "Instalador de MimirSynth"
    if ($From) { $From = (Resolve-Path -LiteralPath $From).Path }
    Test-Docker

    if (-not $Dir) {
        $here = (Get-Location).Path
        if ((Test-Path (Join-Path $here "docker-compose.yml")) -and (Test-Path (Join-Path $here ".env")) -and (Select-String -LiteralPath (Join-Path $here "docker-compose.yml") -Pattern "mimirsynth" -Quiet)) { $Dir = $here }
        else { $Dir = Join-Path $HOME "mimirsynth" }
    }
    New-Item -ItemType Directory -Force -Path $Dir | Out-Null
    $Dir = (Resolve-Path -LiteralPath $Dir).Path
    Set-Location -LiteralPath $Dir
    $hasCompose = Test-Path (Join-Path $Dir "docker-compose.yml"); $hasEnv = Test-Path (Join-Path $Dir ".env")

    if ($hasCompose -and $hasEnv) {
        if ((Get-NativeOutput "docker" @("compose", "ps", "-aq", "mimirsynth")) -join "") {
            Step "Existing installation" "Instalaci\u00f3n existente"
            Say "MimirSynth is already installed in {0}. Nothing was changed." "MimirSynth ya est\u00e1 instalado en {0}. No se ha cambiado nada." @($Dir)
            if (Show-UpgradeVerdict) {
                Say "To upgrade it: run ./update.sh from WSL in that folder, or back up and run 'docker compose pull' and 'docker compose up -d' there (see Upgrading in docs/INSTALL.md)." `
                    "Para actualizarlo: ejecuta ./update.sh desde WSL en esa carpeta, o haz una copia de seguridad y ejecuta all\u00ed 'docker compose pull' y 'docker compose up -d' (ver Actualizar en docs/es/INSTALL.md)."
            }
            return
        }
        Step "Configuration" "Configuraci\u00f3n"
        Say "{0} already has a configuration that has not been started: using it as it is." "{0} ya tiene una configuraci\u00f3n que no se ha arrancado: se usa tal cual." @($Dir)
        $St.Port = [int](Get-EnvValue "MIMIRSYNTH_PORT"); if (-not $St.Port) { $St.Port = 8000 }
        $St.UseOllama = ("," + (Get-EnvValue "COMPOSE_PROFILES") + ",") -like "*,ollama,*"
        $St.GraphType = Get-EnvValue "MIMIRSYNTH_GRAPH_BACKEND"; if (-not $St.GraphType) { $St.GraphType = "falkordb" }
        if ($St.GraphType -eq "neo4j") {
            $u = (Get-EnvValue "MIMIRSYNTH_NEO4J_URI") -replace '^[a-z+]+://', ''
            $St.ContainerHost = $u.Substring(0, $u.LastIndexOf(":")); $St.GraphPort = [int]$u.Substring($u.LastIndexOf(":") + 1)
            $St.Graph = "existing"
        }
        else {
            $St.ContainerHost = Get-EnvValue "MIMIRSYNTH_FALKOR_HOST"; $St.GraphPort = [int](Get-EnvValue "MIMIRSYNTH_FALKOR_PORT")
            $St.Graph = if ($St.ContainerHost -and $St.ContainerHost -ne "falkordb") { "existing" } else { "local" }
        }
    }
    elseif ($hasCompose -or $hasEnv) {
        Fail "{0} has only one of docker-compose.yml and .env: finish or remove that installation, or choose another folder with -Dir" `
             "{0} solo tiene uno de docker-compose.yml y .env: termina o borra esa instalaci\u00f3n, o elige otra carpeta con -Dir" @($Dir)
    }
    else {
        Say "It will be installed in {0}." "Se instalar\u00e1 en {0}." @($Dir)
        Read-GraphChoice
        Read-OllamaChoice
        Select-Port
        Write-Config
        if ($St.Graph -eq "existing") { Test-GraphBeforeStart }
    }

    if ($NoStart) {
        Say "Configuration written. To start it: cd {0}; docker compose up -d   (or run this installer again)" `
            "Configuraci\u00f3n escrita. Para arrancarla: cd {0}; docker compose up -d   (o vuelve a ejecutar este instalador)" @($Dir)
        return
    }

    Step "Start" "Arranque"
    Say "Downloading the images and starting the services (the first time takes a few minutes)..." "Descargando las im\u00e1genes y arrancando los servicios (la primera vez tarda unos minutos)..."
    if ((Dc @("up", "-d")) -ne 0) { Fail "docker compose up failed: see the messages above" "docker compose up ha fallado: mira los mensajes de arriba" }

    if ($St.UseOllama) {
        Step "Embedding model" "Modelo de embeddings"
        for ($i = 0; $i -lt 60 -and (Dc @("exec", "-T", "ollama", "ollama", "list") -Quiet) -ne 0; $i++) { Start-Sleep -Seconds 2 }
        if ((Dc @("exec", "-T", "ollama", "ollama", "pull", $EmbedModel)) -eq 0) { Say "{0} is ready." "{0} est\u00e1 listo." @($EmbedModel) }
        else { Warn "could not download {0}: run 'docker compose exec ollama ollama pull {0}' in {1}" "no se pudo descargar {0}: ejecuta 'docker compose exec ollama ollama pull {0}' en {1}" @($EmbedModel, $Dir) }
    }

    Step "Waiting for MimirSynth" "Esperando a MimirSynth"
    switch (Wait-Health) {
        0 { Say "It answers and reaches its databases." "Responde y llega a sus bases de datos." }
        2 { Warn "it answers, but does not reach everything it needs: {0}" "responde, pero no llega a todo lo que necesita: {0}" @($St.HealthBody) }
        default {
            Dc @("logs", "--tail", "30", "mimirsynth") | Out-Null
            Fail "it did not answer within {0}s: see 'docker compose logs mimirsynth' in {1}" "no ha respondido en {0}s: mira 'docker compose logs mimirsynth' en {1}" @($WaitSeconds, $Dir)
        }
    }

    $St.SetupCode = ""
    if ((Get-Http "http://127.0.0.1:$($St.Port)/api/auth/options").Body -match '"setup":\s*true') {
        for ($i = 0; $i -lt 10 -and -not $St.SetupCode; $i++) { $St.SetupCode = Get-SetupCode; if (-not $St.SetupCode) { Start-Sleep -Seconds 1 } }
    }
    if ($St.Graph -eq "existing" -and -not $St.Probed) { Test-GraphFromContainer }

    $Url = "http://localhost:$($St.Port)"
    # The setup wizard (#361) is at /configuracion. Its API answers 401 without a session; a release without it serves the web app on
    # any path (200), and there /configuracion would be a page that does not exist once the administrator signs in.
    if ((Get-Http "http://127.0.0.1:$($St.Port)/api/setup").Code -in @(401, 403)) { $Url = "$Url/configuracion" }
    Step "Ready" "Listo"
    Say "  Open:             {0}" "  Abre:             {0}" @($Url)
    if ($St.SetupCode) {
        Say "  First-start code: {0}" "  C\u00f3digo de inicio: {0}" @($St.SetupCode)
        Say "  In the browser, enter the code and create the administrator account; the wizard then guides you through the rest." `
            "  En el navegador, introduce el c\u00f3digo y crea la cuenta de administrador; el asistente te gu\u00eda despu\u00e9s en el resto."
    }
    else { Say "  Sign in with your administrator account." "  Entra con tu cuenta de administrador." }
    Say "  Folder:           {0}  (docker compose commands run here)" "  Carpeta:          {0}  (los comandos de docker compose se ejecutan aqu\u00ed)" @($Dir)
    if (-not $NoBrowser) {
        try { if ($OnMac) { Invoke-Native "open" @($Url) -Quiet | Out-Null } else { Start-Process $Url } } catch { }
    }
}
catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    if ($St.Removed) { Write-Host (T "The installer stopped: fix the cause and run it again." "El instalador se ha detenido: corrige la causa y vuelve a ejecutarlo.") }
    else { Write-Host (T "The installer stopped. Nothing was removed: fix the cause and run it again." "El instalador se ha detenido. No se ha borrado nada: corrige la causa y vuelve a ejecutarlo.") }
    $failed = $true
}
finally {
    Pop-Location
    $ErrorActionPreference, $ProgressPreference = $SavedPrefs
}
if ($failed -and $PSCommandPath) { exit 1 }   # only when run as a file: inside `irm | iex` it would close the window
