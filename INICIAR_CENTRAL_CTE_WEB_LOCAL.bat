@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Central CT-e / DACTE - Web Local

set "WEB_SERVER=%~dp0web_local\server.py"
set "WEB_INDEX=%~dp0web_local\static\index.html"

echo.
echo ============================================================
echo   CENTRAL CT-e / DACTE RC27.14 - WEB/WINDOWS MVP10
echo ============================================================
echo.

if not exist "%WEB_SERVER%" (
  echo ERRO: web_local\server.py nao foi encontrado.
  pause
  exit /b 2
)

rem 1) Futuro runtime portatil, caso seja adicionado ao pacote.
if exist "%~dp0web_local\runtime\python.exe" (
  echo Iniciando com o Python portatil do projeto...
  "%~dp0web_local\runtime\python.exe" "%WEB_SERVER%"
  goto :fim
)

rem 2) Python Launcher oficial do Windows.
where py.exe >nul 2>&1
if not errorlevel 1 (
  echo Iniciando o servidor local com py.exe...
  py.exe -3 "%WEB_SERVER%"
  goto :fim
)

rem 3) Python instalado no PATH.
where python.exe >nul 2>&1
if not errorlevel 1 (
  echo Iniciando o servidor local com python.exe...
  python.exe "%WEB_SERVER%"
  goto :fim
)

echo.
echo Python nao foi encontrado neste computador.
echo A interface sera aberta no modo navegador, sem servidor local.
echo Nesse modo, os dados ficam somente neste navegador.
echo.
start "" "%WEB_INDEX%"

goto :fim

:fim
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo O servidor terminou com o codigo %RC%.
  pause
)
exit /b %RC%
