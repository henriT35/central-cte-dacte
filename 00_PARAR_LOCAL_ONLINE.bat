@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Central CT-e - Parar Local Online
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp000_PARAR_LOCAL_ONLINE.ps1"
pause
