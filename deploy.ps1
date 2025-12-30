# deploy.ps1 - filereaderapi 一键部署脚本
# 使用方法示例：
#   .\deploy.ps1 -ImageName "filereaderapi" -ImageTag "latest" -Registry "registry.example.com" -RemoteHost "192.168.1.10" -RemoteUser "root"
#   .\deploy.ps1 -ImageName "filereaderapi" -ImageTag "latest" -RemoteHost "192.168.1.10" -RemoteUser "root"

param(
    [string]$ImageName = "filereaderapi",                        # 镜像名称（不含 tag）
    [string]$ImageTag = "latest",                               # 镜像 Tag
    [string]$Registry = "",                                     # 可选：如果需要先 docker login 一个 registry，可以在这里指定（本地直连服务器时一般留空）
    [string]$ProxyHost = "192.168.1.198:10811",                # HTTP/HTTPS 代理地址（与 agent 脚本保持一致）
    [string]$DockerHost = "192.168.1.10:2375",                 # Docker Host（与 agent 脚本保持一致）
    [string]$RemoteHost = "192.168.1.10",                      # 远程服务器地址
    [string]$RemoteUser = "root",                              # 远程服务器用户
    [string]$RemoteProjectPath = "/fskj/workspace/filereaderapi",  # 远程项目路径
    [string]$SshKeyPath = "",                                   # SSH 私钥路径，为空则走默认 ssh 配置
    [switch]$SkipRemoteDeploy = $false                         # 是否跳过远程部署
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
if (-not $ProjectRoot) {
    $ProjectRoot = Get-Location
}

$FullImageName = if ($ImageTag -and $ImageTag -ne "") {"$ImageName`:$ImageTag"} else {$ImageName}

# 简单的进度显示
$TotalSteps = 3
if (-not $SkipRemoteDeploy) { $TotalSteps += 1 }
$CurrentStep = 0

function Step {
    param(
        [string]$Title
    )
    $script:CurrentStep++
    Write-Host "[${CurrentStep}/${TotalSteps}] $Title" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Msg)
    Write-Host "✓ $Msg" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Msg)
    Write-Host "错误: $Msg" -ForegroundColor Red
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host " filereaderapi 一键部署" -ForegroundColor Cyan
Write-Host " 项目路径: $ProjectRoot" -ForegroundColor Cyan
Write-Host " 镜像: $FullImageName" -ForegroundColor Cyan
Write-Host " 远程: ${RemoteUser}@${RemoteHost} ($RemoteProjectPath)" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# 步骤0: 设置代理和 Docker Host 环境变量（保持与 G:\agent\deploy.ps1 一致）
Step "设置代理和 Docker Host 环境变量"
$env:HTTP_PROXY = "http://$ProxyHost"
$env:HTTPS_PROXY = "http://$ProxyHost"
$env:DOCKER_HOST = "tcp://$DockerHost"
Write-Success "已设置 HTTP_PROXY=$($env:HTTP_PROXY)"
Write-Success "已设置 HTTPS_PROXY=$($env:HTTPS_PROXY)"
Write-Success "已设置 DOCKER_HOST=$($env:DOCKER_HOST)"

# 步骤1: 构建 Docker 镜像
Step "构建 Docker 镜像 ($FullImageName)"
try {
    Set-Location $ProjectRoot

    if (-not (Test-Path "$ProjectRoot/Dockerfile")) {
        throw "未找到 Dockerfile，请确认当前目录存在 Dockerfile"
    }

    Write-Host "执行命令: docker build -t $FullImageName ." -ForegroundColor Yellow
    docker build -t $FullImageName .

    if ($LASTEXITCODE -ne 0) {
        throw "docker build 失败，退出码: $LASTEXITCODE"
    }
    Write-Success "Docker 镜像构建成功 ($FullImageName)"
} catch {
    Write-ErrorMsg "构建镜像失败: $_"
    exit 1
} finally {
    Set-Location $ProjectRoot
}

# 步骤2: docker login（如果指定了 Registry）
if ($Registry -and $Registry -ne "") {
    Step "登录 Docker Registry ($Registry)"
    try {
        Write-Host "如果需要账号密码，请在弹出的提示中输入，或事先 docker login" -ForegroundColor Yellow
        docker login $Registry
        if ($LASTEXITCODE -ne 0) {
            throw "docker login 失败，退出码: $LASTEXITCODE"
        }
        Write-Success "docker login 成功 ($Registry)"
    } catch {
        Write-ErrorMsg "docker login 失败: $_"
        exit 1
    }
}

# 步骤3: 远程部署（通过 ssh 在远程执行 docker compose 命令）
if (-not $SkipRemoteDeploy) {
    Step "远程部署到 ${RemoteUser}@${RemoteHost}"

    $sshCmd = Get-Command ssh -ErrorAction SilentlyContinue
    if (-not $sshCmd) {
        Write-ErrorMsg "未找到 ssh 命令，请先在 Windows 上安装 OpenSSH 客户端 (可在系统可选功能中启用)"
        exit 1
    }

    $sshDir = "$env:USERPROFILE\.ssh"
    if (-not (Test-Path $sshDir)) {
        New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
    }

    $sshOptions = @(
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "UserKnownHostsFile=$sshDir\known_hosts",
        "-o", "BatchMode=yes",
        "-o", "PasswordAuthentication=no"
    )

    $keyPath = $null
    if ($SshKeyPath -and (Test-Path $SshKeyPath)) {
        $keyPath = (Resolve-Path $SshKeyPath).Path
        $sshOptions += "-i", $keyPath
        Write-Host "使用指定私钥: $keyPath" -ForegroundColor Yellow
    } else {
        $defaultKeyEd25519 = Join-Path $sshDir "id_ed25519"
        $defaultKeyRsa = Join-Path $sshDir "id_rsa"
        if (Test-Path $defaultKeyEd25519) {
            $keyPath = (Resolve-Path $defaultKeyEd25519).Path
            $sshOptions += "-i", $keyPath
            Write-Host "使用默认私钥: $keyPath" -ForegroundColor Yellow
        } elseif (Test-Path $defaultKeyRsa) {
            $keyPath = (Resolve-Path $defaultKeyRsa).Path
            $sshOptions += "-i", $keyPath
            Write-Host "使用默认私钥: $keyPath" -ForegroundColor Yellow
        } else {
            Write-Host "未找到私钥文件，将使用 ssh 默认配置" -ForegroundColor Yellow
        }
    }

    # 远程命令：cd 到项目目录后执行 docker compose down 和 up -d
    $remoteCmd = @(
        "cd $RemoteProjectPath",
        "docker compose down",
        "docker compose up -d"
    ) -join '; '

    Write-Host "将在远程执行: $remoteCmd" -ForegroundColor Yellow

    try {
        & ssh @sshOptions "${RemoteUser}@${RemoteHost}" "$remoteCmd"
        if ($LASTEXITCODE -ne 0) {
            throw "ssh 远程部署命令失败，退出码: $LASTEXITCODE"
        }
        $remoteInfo = "${RemoteUser}@${RemoteHost}:${RemoteProjectPath}"
        Write-Success "远程部署完成 ($remoteInfo)"
    } catch {
        Write-ErrorMsg "远程部署失败: $_"
        exit 1
    }
}

Write-Host "========================================" -ForegroundColor Green
Write-Host " 部署流程执行完毕" -ForegroundColor Green
Write-Host " 镜像: $FullImageName" -ForegroundColor Green
if (-not $SkipRemoteDeploy) {
    $deployInfo = "${RemoteUser}@${RemoteHost}:${RemoteProjectPath}"
    Write-Host " 已部署到: $deployInfo" -ForegroundColor Green
}
Write-Host "========================================" -ForegroundColor Green

