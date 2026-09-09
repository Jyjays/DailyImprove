@echo off
chcp 936 >nul
setlocal
cd /d "%~dp0"
title DailyImprove 学习台

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Node.js，请先安装: https://nodejs.org/
  pause
  exit /b 1
)

if not exist "node_modules\vite" (
  echo 首次启动，正在安装依赖，请稍候...
  call npm install
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络与 Node.js 环境。
    pause
    exit /b 1
  )
)

REM 代理绕过（vite 转发本机后端时需要）
set "NO_PROXY=127.0.0.1,localhost"
set "no_proxy=127.0.0.1,localhost"

echo 学习平台正在启动: http://127.0.0.1:4173
echo 说明：本脚本只启动前端，数据来自后端 http://127.0.0.1:8000
echo       若页面加载不出数据，请改用项目根目录的「启动学习台.bat」
start "" http://127.0.0.1:4173
call node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 4173
pause
