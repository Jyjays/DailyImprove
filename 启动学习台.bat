@echo off
REM ============================================
REM  松的学习台 —— 一键启动（后端 + 前端）
REM  会弹出两个窗口，不要关。浏览器打开 http://127.0.0.1:4173
REM ============================================

set "ROOT=%~dp0"
set "PY=%ROOT%.venv\Scripts\python.exe"
set "NODE=C:\Users\Jyjays\.workbuddy\binaries\node\versions\22.22.2-2\node.exe"

echo.
echo [1/2] 启动后端  127.0.0.1:8000 ...
start "DailyImprove-Backend" cmd /k ""%PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000"

REM 等后端起来
timeout /t 5 /nobreak >nul

echo [2/2] 启动前端  127.0.0.1:4173 ...
cd /d "%ROOT%test1\test1"

REM NO_PROXY 必须设：否则 vite 的 proxy 会走系统代理，转发到本机 8000 被拒（502）
start "Study-Frontend" cmd /k "set NO_PROXY=127.0.0.1,localhost&& set no_proxy=127.0.0.1,localhost&& "%NODE%" node_modules/vite/bin/vite.js --host 127.0.0.1 --port 4173"

timeout /t 6 /nobreak >nul
echo.
echo 启动完成，正在打开浏览器...
start http://127.0.0.1:4173
echo.
echo 如果页面空白，等 5 秒刷新一次（前端首次编译需要时间）。
pause
