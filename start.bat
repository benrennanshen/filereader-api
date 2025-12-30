@echo off
setlocal ENABLEEXTENSIONS ENABLEDELAYEDEXPANSION
chcp 65001 >nul
title filereader 服务
color 0A

set "APP_ENTRY=main:app"
set "HOST=0.0.0.0"
set "PORT=8002"
set "PYTHON=python"
set "VENV_DIR=.venv"
set "ACTIVATE=%VENV_DIR%\Scripts\activate.bat"
set "PIP_BIN=%VENV_DIR%\Scripts\pip.exe"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"

:menu
cls
echo ====================================
echo     filereader 服务管理
echo ====================================
echo.
echo   1. 启动服务（普通模式）
echo   2. 启动服务（开发模式/热重载）
echo   3. 停止服务
echo   4. 退出
echo.
echo ====================================
set /p choice=请选择 (1-4): 

if "%choice%"=="1" goto start
if "%choice%"=="2" goto start_dev
if "%choice%"=="3" goto stop
if "%choice%"=="4" goto end
echo 无效选择，请重试
timeout /t 2 >nul
goto menu

:start
cls
echo ====================================
echo     启动服务（普通模式）
echo ====================================
echo.
call :prepare_env
if errorlevel 1 (
    echo.
    echo ❌ 环境准备失败，请检查上述错误信息
    echo.
    pause
    goto menu
)
call :run_server
goto menu

:start_dev
cls
echo ====================================
echo   启动服务（开发模式/热重载）
echo ====================================
echo.
call :prepare_env
if errorlevel 1 (
    echo.
    echo ❌ 环境准备失败，请检查上述错误信息
    echo.
    pause
    goto menu
)
call :run_server dev
goto menu

:prepare_env
echo [1/5] 检查并关闭旧进程...
call :kill_port %PORT%
if errorlevel 1 (
    echo ⚠️ 关闭旧进程时出现问题，继续执行...
)
echo.

echo [2/5] 等待端口释放...
timeout /t 2 /nobreak >nul
echo.

echo [3/5] 激活/创建虚拟环境...
call :ensure_venv
if errorlevel 1 (
    echo ❌ 虚拟环境准备失败
    exit /b 1
)
echo.

echo [4/5] 安装/更新依赖...
call :install_deps
if errorlevel 1 (
    echo ⚠️ 依赖安装失败，但继续启动...
)
echo.
exit /b 0

:run_server
echo [5/5] 启动服务...
echo.
echo ====================================
echo   服务地址: http://localhost:%PORT%
echo   按 Ctrl+C 可停止服务
echo ====================================
echo.
if exist "%VENV_PYTHON%" (
    set "RUN_PYTHON=%VENV_PYTHON%"
) else (
    set "RUN_PYTHON=%PYTHON%"
)
if "%~1"=="dev" (
    "%RUN_PYTHON%" -m uvicorn %APP_ENTRY% --host %HOST% --port %PORT% --reload
) else (
    "%RUN_PYTHON%" -m uvicorn %APP_ENTRY% --host %HOST% --port %PORT%
)
echo.
echo 服务已停止
pause
exit /b 0

:ensure_venv
if not exist "%ACTIVATE%" (
    echo ⚠️ 未找到虚拟环境，正在创建 %VENV_DIR% ...
    %PYTHON% -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo ❌ 创建虚拟环境失败，请检查 Python 安装
        exit /b 1
    )
)

if not exist "%ACTIVATE%" (
    echo ❌ 仍未找到虚拟环境脚本
    exit /b 1
)
call "%ACTIVATE%"
if errorlevel 1 (
    echo ❌ 激活虚拟环境失败
    exit /b 1
)
echo ✅ 虚拟环境已就绪
exit /b 0

:install_deps
if not exist "requirements.txt" (
    echo ⚠️ 未找到 requirements.txt 文件，跳过依赖安装
    exit /b 0
)
if exist "%PIP_BIN%" (
    "%PIP_BIN%" install -r requirements.txt --quiet --disable-pip-version-check
) else (
    pip install -r requirements.txt --quiet --disable-pip-version-check
)
if errorlevel 1 (
    echo ⚠️ 依赖安装失败（继续启动，但可能影响服务运行）
    exit /b 1
)
echo ✅ 依赖已更新
exit /b 0

:kill_port
set "TARGET_PORT=%1"
set "FOUND=0"
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /R /C:":%TARGET_PORT% .*LISTENING"') do (
    echo 发现端口 %TARGET_PORT% 对应 PID %%p，正在终止...
    taskkill /PID %%p /F >nul 2>&1
    set "FOUND=1"
)
if "!FOUND!"=="1" (
    echo ✅ 端口 %TARGET_PORT% 已清理
) else (
    echo 🔹 未检测到占用端口 %TARGET_PORT% 的进程
)
exit /b 0

:stop
cls
echo ====================================
echo     停止服务
echo ====================================
echo.
call :kill_port %PORT%
echo.
pause
goto menu

:end
echo.
echo 再见！
timeout /t 1 >nul
exit /b 0
