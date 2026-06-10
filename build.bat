@echo off
echo ============================================================
echo  DataClarify Build Script v1.2
echo ============================================================

echo Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build

echo Running PyInstaller...
pyinstaller DataClarify.spec --clean
if errorlevel 1 (
    echo PyInstaller failed. Aborting.
    pause
    exit /b 1
)

echo Copying config.txt to dist...
copy /y config.txt dist\DataClarify\config.txt

echo Waiting for file locks to release...
timeout /t 3 /nobreak > nul

echo Creating ZIP...
powershell -Command "Compress-Archive -Path 'dist\DataClarify' -DestinationPath 'DataClarify-v1.2.0.zip' -Force"
if errorlevel 1 (
    echo ZIP creation failed.
    pause
    exit /b 1
)

echo ============================================================
echo  Build complete: DataClarify-v1.2.0.zip
echo ============================================================
pause
