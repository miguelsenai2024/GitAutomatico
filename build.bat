@echo off
chcp 65001 > nul
title GitAutomatico - Build EXE
cls

echo ============================================================
echo   GitAutomatico - Compilador para .EXE
echo ============================================================
echo.

REM Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] Python nao encontrado no PATH!
    echo     Instale em: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1/4] Criando ambiente virtual...
if not exist ".venv\" (
    python -m venv .venv
)

echo [2/4] Ativando ambiente e instalando dependencias...
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [X] Falha ao instalar dependencias.
    pause
    exit /b 1
)

echo [3/4] Limpando builds anteriores...
if exist "build\"  rmdir /s /q build
if exist "dist\"   rmdir /s /q dist

echo [4/4] Compilando com PyInstaller...
pyinstaller ^
    --onefile ^
    --console ^
    --name GitAutomatico ^
    --collect-all rich ^
    --collect-all questionary ^
    --hidden-import tkinter ^
    --hidden-import tkinter.filedialog ^
    --noconfirm ^
    --clean ^
    git_automatico.py

if errorlevel 1 (
    echo.
    echo [X] Erro na compilacao!
    pause
    exit /b 1
)

echo.
echo ============================================================
echo   [OK] Compilacao concluida com sucesso!
echo ============================================================
echo.
echo   Arquivo gerado: dist\GitAutomatico.exe
echo.
echo   Na primeira execucao, o programa vai pedir seu token do GitHub.
echo   Ele sera salvo em: %%LOCALAPPDATA%%\GitAuto\token.dat
echo.
pause
