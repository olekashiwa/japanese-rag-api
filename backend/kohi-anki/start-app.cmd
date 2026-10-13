@echo off
chcp 65001 >nul
rem Запуск тренажёра слов и фраз романа «コーヒーが冷めないうちに».
rem Требуется Node.js 20+ и pnpm (или npm).
cd /d "%~dp0"

where pnpm >nul 2>nul
if %errorlevel%==0 (
  set "PM=pnpm"
) else (
  where npm >nul 2>nul
  if %errorlevel%==0 (
    set "PM=npm"
  ) else (
    echo Не найден ни pnpm, ни npm. Установите Node.js: https://nodejs.org
    pause
    exit /b 1
  )
)

if not exist "node_modules" (
  echo Устанавливаю зависимости через %PM% ...
  call %PM% install
  if errorlevel 1 (
    echo Не удалось установить зависимости.
    pause
    exit /b 1
  )
)

echo Запускаю приложение. Откройте адрес, который выведет Vite.
call %PM% run dev
pause
