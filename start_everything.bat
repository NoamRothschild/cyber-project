@echo off
setlocal

:: ========== Setup (run once) ==========
echo.
echo [1/4] Running setup_dev.py...
python setup_dev.py
if errorlevel 1 exit /b 1

echo.
echo [2/4] Running setup_redis.py...
python setup_redis.py
if errorlevel 1 exit /b 1

echo.
echo [3/4] Creating auth keys...
python create_auth_keys.py
if errorlevel 1 exit /b 1

echo.
echo [4/4] Starting servers (Ctrl+C or close window will stop all)...
echo.

:: Start servers and keep their PIDs; on Ctrl+C or window close, PowerShell finally-block kills them
powershell -NoProfile -Command ^
  "$ErrorActionPreference = 'Stop'; ^
   $auth = Start-Process -FilePath 'python' -ArgumentList 'auth_server.py' -WorkingDirectory 'auth_server' -PassThru -WindowStyle Hidden; ^
   $chat = Start-Process -FilePath 'python' -ArgumentList 'chat-s.py' -WorkingDirectory 'chat-server' -PassThru -WindowStyle Hidden; ^
   $region = Start-Process -FilePath 'python' -ArgumentList 'region_server.py' -WorkingDirectory 'region_server' -PassThru -WindowStyle Hidden; ^
   $pids = @($auth.Id, $chat.Id, $region.Id); ^
   Write-Host 'Servers started (PIDs: ' ($pids -join ', ') ')'; ^
   try { Read-Host 'Press Enter to stop all servers' } ^
   finally { foreach ($p in $pids) { Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }; Write-Host 'All servers stopped.' }"

endlocal
