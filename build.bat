@echo off
REM ============================================================
REM  build.bat — Package Jeopardy Game with PyInstaller
REM  Output: dist\JeopardyGame\JeopardyGame.exe
REM ============================================================

echo [BUILD] Installing / upgrading requirements...
pip install -r requirements.txt

echo [BUILD] Running PyInstaller...
pyinstaller ^
    --name "Chaewon Jeopardy" ^
    --windowed ^
    --onedir ^
    --icon "icon.ico" ^
    --add-data "icon.ico;." ^
    --add-data "assets;assets" ^
    --collect-all PyQt6 ^
    main.py

echo.
if exist "dist\Chaewon Jeopardy\Chaewon Jeopardy.exe" (
    echo [BUILD] SUCCESS — dist\Chaewon Jeopardy\Chaewon Jeopardy.exe
) else (
    echo [BUILD] FAILED — check output above for errors.
)
pause
