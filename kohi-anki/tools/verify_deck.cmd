@echo off
rem ===========================================================================
rem  verify_deck.cmd - проверка собранной колоды Anki.
rem
rem  Запуск:  tools\verify_deck.cmd
rem  Код возврата: 0 - проверка пройдена, 1 - не пройдена.
rem
rem  ВАЖНО: файл сохранён в UTF-8 с переводами строк CRLF.
rem ===========================================================================
chcp 65001 >nul 2>&1
setlocal EnableExtensions

set "ANKI_PY=%LOCALAPPDATA%\AnkiProgramFiles\.venv\Scripts\python.exe"

if not exist "%ANKI_PY%" goto :no_python

pushd "%~dp0.."
if errorlevel 1 goto :no_root

echo Интерпретатор : "%ANKI_PY%"
echo Каталог сборки: "%CD%"
echo.

"%ANKI_PY%" "tools\verify_deck.py" %*
set "RC=%ERRORLEVEL%"

popd
if not "%RC%"=="0" echo [ОШИБКА] Проверка колоды завершилась с кодом %RC%.
endlocal & exit /b %RC%

:no_python
echo.
echo [ОШИБКА] Не найден Python-интерпретатор Anki.
echo.
echo   Ожидался файл:
echo     "%ANKI_PY%"
echo.
echo   Установите Anki 25.x с https://apps.ankiweb.net/, запустите её
echo   хотя бы один раз и повторите проверку.
echo.
endlocal & exit /b 1

:no_root
echo [ОШИБКА] Не удалось перейти в корень проекта "%~dp0..".
endlocal & exit /b 1
