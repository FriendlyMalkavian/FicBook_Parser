@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ============================================
echo  FicBook Parser v0.11 — Установка
echo ============================================
echo.

set "APP_DIR=%LOCALAPPDATA%\FicBookParser"

if not exist "%APP_DIR%" mkdir "%APP_DIR%"

copy /Y "%~dp0dist\FicBookParser.exe" "%APP_DIR%\FicBookParser.exe" >nul
if errorlevel 1 (
    echo [ERROR] Не удалось скопировать файл.
    pause
    exit /b 1
)

set "SHORTCUT=%APPDATA%\Microsoft\Windows\Start Menu\Programs\FicBook Parser.lnk"
if not exist "%SHORTCUT%" (
    powershell -Command ^
        "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%');" ^
        "$s.TargetPath='%APP_DIR%\FicBookParser.exe';" ^
        "$s.WorkingDirectory='%APP_DIR%';" ^
        "$s.Description='Скачивание фанфиков с ficbook.net';" ^
        "$s.Save()" >nul
)

echo  Установка завершена!
echo.
echo  Приложение установлено в: %APP_DIR%
echo  Ярлык добавлен в меню Пуск.
echo.
pause
