@echo off
rem ===========================================================================
rem  build_deck.cmd - сборка колоды Anki для романа «コーヒーが冷めないうちに».
rem
rem  Запуск:  tools\build_deck.cmd
rem  Скрипт сам переходит в корень проекта и вызывает tools\build_deck.py
rem  интерпретатором Python из установленной Anki.
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

"%ANKI_PY%" "tools\build_deck.py" %*
set "RC=%ERRORLEVEL%"

popd
if not "%RC%"=="0" echo [ОШИБКА] Сборка колоды завершилась с кодом %RC%.
endlocal & exit /b %RC%

:no_python
echo.
echo [ОШИБКА] Не найден Python-интерпретатор Anki.
echo.
echo   Ожидался файл:
echo     "%ANKI_PY%"
echo.
echo   Что делать:
echo     1. Установите Anki 25.x с https://apps.ankiweb.net/
echo     2. Запустите Anki хотя бы один раз - она создаст свою среду Python.
echo     3. Если Anki установлена в другое место, задайте путь вручную:
echo          set "ANKI_PY=C:\путь\к\AnkiProgramFiles\.venv\Scripts\python.exe"
echo          tools\build_deck.cmd
echo.
endlocal & exit /b 1

:no_root
echo [ОШИБКА] Не удалось перейти в корень проекта "%~dp0..".
endlocal & exit /b 1
