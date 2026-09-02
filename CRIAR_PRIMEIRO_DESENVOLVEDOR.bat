@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Central CT-e - Criar primeiro Desenvolvedor

echo.
echo ============================================================
echo   CRIAR PRIMEIRO PERFIL DESENVOLVEDOR
echo ============================================================
echo.
echo Feche antes a janela do servidor da Central CT-e.
echo Esta operacao funciona somente neste computador.
echo.
pause

if exist "%~dp0web_local\runtime\python.exe" (
  "%~dp0web_local\runtime\python.exe" "%~dp0web_local\create_first_developer.py"
  goto :fim
)

where py.exe >nul 2>&1
if not errorlevel 1 (
  py.exe -3 "%~dp0web_local\create_first_developer.py"
  goto :fim
)

where python.exe >nul 2>&1
if not errorlevel 1 (
  python.exe "%~dp0web_local\create_first_developer.py"
  goto :fim
)

echo.
echo ERRO: Python nao foi encontrado.

:fim
echo.
pause
