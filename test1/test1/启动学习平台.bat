@echo off
chcp 65001 >nul
cd /d "%~dp0"
title 数析研习所

if not exist "node_modules" (
  echo 首次启动，正在安装学习平台依赖，请稍候...
  call npm install
  if errorlevel 1 (
    echo 依赖安装失败，请检查网络与 Node.js 环境。
    pause
    exit /b 1
  )
)

echo 学习平台正在启动：http://localhost:4173
start "" /b powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://localhost:4173'"
call npm run dev
