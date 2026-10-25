@echo off
chcp 936 >nul
setlocal
title DailyImprove 学习台

set "STUDY_ROOT=%~dp0"
if "%STUDY_ROOT:~-1%"=="\" set "STUDY_ROOT=%STUDY_ROOT:~0,-1%"
set "STUDY_PY=%STUDY_ROOT%\.venv\Scripts\python.exe"

if not exist "%STUDY_PY%" (
  echo [错误] 未找到虚拟环境: %STUDY_PY%
  echo 请先在项目根目录创建 .venv 并安装项目依赖。
  pause
  exit /b 1
)

REM 在当前控制台运行主程序，前后端由它隐藏启动并统一管理。
"%STUDY_PY%" "%STUDY_ROOT%\scripts\start_study.py"
set "STUDY_EXIT_CODE=%ERRORLEVEL%"
if not "%STUDY_EXIT_CODE%"=="0" pause
exit /b %STUDY_EXIT_CODE%
