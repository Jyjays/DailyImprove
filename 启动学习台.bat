@echo off
chcp 936 >nul
setlocal
REM ============================================
REM  DailyImprove 学习台 - 一键启动（后端 + 前端）
REM  会弹出两个窗口，不要关。浏览器打开 http://127.0.0.1:4173
REM ============================================

set "ROOT=%~dp0"
REM %~dp0 结尾带反斜杠，会让 "%ROOT%" 变成 "...\" 从而转义掉结束引号，必须去掉
if "%ROOT:~-1%"=="\" set "ROOT=%ROOT:~0,-1%"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "WEB=%ROOT%\test1\test1"

if not exist "%PY%" (
  echo [错误] 未找到虚拟环境: %PY%
  echo 请先在项目根目录执行:
  echo     python -m venv .venv
  echo     .venv\Scripts\python.exe -m pip install -e .
  pause
  exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 Node.js，请先安装: https://nodejs.org/
  pause
  exit /b 1
)

if not exist "%WEB%\node_modules\vite" (
  echo [错误] 前端依赖未安装: %WEB%\node_modules
  echo 请执行: cd "%WEB%" 然后 npm install
  pause
  exit /b 1
)

REM 代理绕过：start 开的子窗口会继承这两个变量，vite 转发本机后端时必须直连
set "NO_PROXY=127.0.0.1,localhost"
set "no_proxy=127.0.0.1,localhost"

echo.
echo [1/2] 启动后端  http://127.0.0.1:8000 ...
start "DailyImprove-Backend" /D "%ROOT%" cmd /k ".venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

timeout /t 5 /nobreak >nul

echo [2/2] 启动前端  http://127.0.0.1:4173 ...
start "Study-Frontend" /D "%WEB%" cmd /k "node node_modules\vite\bin\vite.js --host 127.0.0.1 --port 4173"

timeout /t 6 /nobreak >nul
echo.
echo 启动完成，正在打开浏览器...
start "" http://127.0.0.1:4173
echo.
echo 如果页面空白，等 5 秒刷新一次（前端首次编译需要时间）。
echo 两个黑窗口分别是后端与前端，关掉即停止服务。
pause
