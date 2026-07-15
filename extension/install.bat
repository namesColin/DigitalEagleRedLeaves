@echo off
setlocal enabledelayedexpansion
set EXT_DIR=%~dp0
set HOST_NAME=com.digitaleagle.agent
set MANIFEST_DIR=%LOCALAPPDATA%\Google\Chrome\User Data\NativeMessagingHosts
set MANIFEST_FILE=%MANIFEST_DIR%\%HOST_NAME%.json
set VENV_PYTHON=%EXT_DIR%..\.venv\Scripts\python.exe
set NATIVE_HOST_SCRIPT=%EXT_DIR%..\src\agent\native_host.py

if not exist "%MANIFEST_DIR%" mkdir "%MANIFEST_DIR%"

(
echo {
echo   "name": "%HOST_NAME%",
echo   "description": "Digital Eagle Agent Bridge",
echo   "path": "%VENV_PYTHON:\=\\%",
echo   "type": "stdio",
echo   "args": ["%NATIVE_HOST_SCRIPT:\=\\%"]
echo }
) > "%MANIFEST_FILE%"

echo Native Host manifest written to: %MANIFEST_FILE%
echo.
echo === Next Steps ===
echo 1. Open chrome://extensions/
echo 2. Enable "Developer mode" (top right)
echo 3. Click "Load unpacked" and select: %EXT_DIR%
echo 4. Copy the extension ID shown
echo 5. Edit %MANIFEST_FILE%
echo 6. Add: "allowed_origins": ["chrome-extension://YOUR_EXTENSION_ID/"]
echo 7. Reload the extension in chrome://extensions/
echo.
pause
