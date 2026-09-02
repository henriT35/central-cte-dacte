@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Central CT-e R12.13.8 - LOCAL + ONLINE

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp000_INICIAR_LOCAL_ONLINE.ps1"
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo O inicializador terminou com codigo %RC%.
  pause
)
exit /b %RC%
