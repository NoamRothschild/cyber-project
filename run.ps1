# Run script for cyber-project services
# Usage: .\run.ps1 redis | auth <redis_host> | chat <redis_host> | region <server_id> <redis_host>
#
# Run from project root.

param(
    [Parameter(Mandatory=$false, Position=0)]
    [ValidateSet("redis", "auth", "chat", "region", "ips", "init", "")]
    [string]$Command = "",
    [Parameter(Position=1)][string]$Arg1,
    [Parameter(Position=2)][string]$Arg2
)

$ErrorActionPreference = "Stop"

if (-not $Command) {
    Write-Host "Usage: .\run.ps1 <command> [args]"
    Write-Host ""
    Write-Host "Commands:"
    Write-Host "  init               Run setup_dev.py and create_auth_keys.py"
    Write-Host "  redis              Start Redis (Docker), run setup_redis.py, print connection info"
    Write-Host "  auth <redis_host>  Build and run auth server (REDIS_HOST from arg)"
    Write-Host "  chat <redis_host>  Build and run chat server (REDIS_HOST from arg)"
    Write-Host "  region <id> <host> Build and run region server (server_id, REDIS_HOST)"
    Write-Host "  ips               Print all LAN IPs for this machine"
    Write-Host ""
    Write-Host "Examples:"
    Write-Host "  .\run.ps1 redis"
    Write-Host "  .\run.ps1 auth 127.0.0.1"
    Write-Host "  .\run.ps1 auth redis"
    Write-Host "  .\run.ps1 region 0 redis"
    exit 0
}
$ProjectRoot = $PSScriptRoot
$ProjectName = (Get-Item $ProjectRoot).Name
$NetworkName = "${ProjectName}_default"

function Get-LanIPs {
    try {
        $ips = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.AddressState -eq "Preferred" } |
            Select-Object -ExpandProperty IPAddress -Unique
        if ($ips) { return $ips }
    } catch { }
    [System.Net.Dns]::GetHostAddresses([System.Net.Dns]::GetHostName()) |
        Where-Object { $_.AddressFamily -eq "InterNetwork" -and $_.IPAddressToString -notlike "127.*" } |
        Select-Object -ExpandProperty IPAddressToString -Unique
}

# Ensure Docker network exists (idempotent - no error if already exists)
function Ensure-Network {
    docker network inspect $NetworkName 2>$null | Out-Null
    if ($LASTEXITCODE -ne 0) { docker network create $NetworkName | Out-Null }
}

# When container needs to reach host's localhost (e.g. redis on host port)
function Resolve-RedisHostForContainer {
    param([string]$HostOrIp)
    if ($HostOrIp -eq "127.0.0.1" -or $HostOrIp -eq "localhost") {
        return "host.docker.internal"
    }
    return $HostOrIp
}

switch ($Command) {
    "init" {
        Set-Location $ProjectRoot
        Write-Host "Running setup_dev.py..."
        python setup_dev.py
        if ($LASTEXITCODE -ne 0) { throw "setup_dev.py failed" }
        Write-Host "Running create_auth_keys.py..."
        python create_auth_keys.py
        if ($LASTEXITCODE -ne 0) { throw "create_auth_keys.py failed" }
        Write-Host "Init complete."
    }

    "redis" {
        Write-Host "Starting Redis (with password)..."
        Set-Location $ProjectRoot
        # docker rm -f redis-auth-session 2>$null
        Ensure-Network
        docker compose up -d --force-recreate redis

        Write-Host "Waiting for Redis to be ready..."
        Start-Sleep -Seconds 3

        Write-Host "Running setup_redis.py (host, port 6379)..."
        $env:REDIS_HOST = "127.0.0.1"
        $env:REDIS_PORT = "6379"
        python setup_redis.py
        if ($LASTEXITCODE -ne 0) {
            throw "setup_redis.py failed"
        }

        Write-Host ""
        Write-Host "Redis is ready. Port 6379 (host), 6379 (Docker internal)."
        Write-Host "  From this machine:        127.0.0.1:6379"
        $lanIps = Get-LanIPs
        if ($lanIps) {
            foreach ($ip in $lanIps) {
                Write-Host "  From LAN:                 ${ip}:6379"
            }
        } else {
            Write-Host "  From LAN:                 <this PC's IP>:6379"
        }
        Write-Host "  From Docker containers:  redis:6379 (same network only)"
    }

    "auth" {
        if (-not $Arg1) {
            throw "Usage: .\run.ps1 auth <redis_host>"
        }
        $redisHost = Resolve-RedisHostForContainer $Arg1
        Write-Host "Building auth server..."
        Set-Location $ProjectRoot
        docker build -f auth_server/Dockerfile -t cyber-auth-server .

        Ensure-Network
        Write-Host "Running auth server (REDIS_HOST=$redisHost)..."
        docker run -d `
            --name auth-server `
            --network $NetworkName `
            -p 9999:9999 `
            -e REDIS_HOST=$redisHost `
            -e AUTH_BIND=0.0.0.0 `
            cyber-auth-server
    }

    "chat" {
        if (-not $Arg1) {
            throw "Usage: .\run.ps1 chat <redis_host>"
        }
        $redisHost = Resolve-RedisHostForContainer $Arg1
        Write-Host "Building chat server..."
        Set-Location $ProjectRoot
        docker build -f chat-server/Dockerfile -t cyber-chat-server .

        Ensure-Network
        Write-Host "Running chat server (REDIS_HOST=$redisHost)..."
        docker run -d `
            --name chat-server `
            --network $NetworkName `
            -p 8888:8888 `
            -e REDIS_HOST=$redisHost `
            cyber-chat-server
    }

    "region" {
        if (-not $Arg1 -or -not $Arg2) {
            throw "Usage: .\run.ps1 region <server_id> <redis_host>"
        }
        $serverId = $Arg1
        $redisHost = Resolve-RedisHostForContainer $Arg2
        Write-Host "Building region server..."
        Set-Location $ProjectRoot
        docker build -f region_server/Dockerfile -t cyber-region-server .

        Ensure-Network
        $tcpPort = 8085 + [int]$serverId
        $udpPort = 8086 + [int]$serverId
        # docker rm -f "region-server-$serverId" 2>$null
        Write-Host "Running region server (server_id=$serverId, REDIS_HOST=$redisHost)..."
        docker run -d `
            --name "region-server-$serverId" `
            --network $NetworkName `
            -p "${tcpPort}:8085" `
            -p "${udpPort}:8086/udp" `
            -e server_id=$serverId `
            -e REDIS_HOST=$redisHost `
            cyber-region-server
    }

    "ips" {
        $lanIps = Get-LanIPs
        if ($lanIps) {
            Write-Host "LAN IPs:"
            foreach ($ip in $lanIps) {
                Write-Host "  $ip"
            }
        } else {
            Write-Host "No LAN IPs found."
        }
    }
}
