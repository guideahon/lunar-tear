@echo off
setlocal

cd /d "%~dp0"

set "HOST=192.168.1.36"
set "HTTP_PORT=8080"
set "GRPC_PORT=8003"
set "AUTH_PORT=3000"

start "Lunar Tear Auth Server" cmd /k "cd /d %~dp0 && auth-server.exe --port %AUTH_PORT% --db db/auth.db"

lunar-tear.exe ^
  --host %HOST% ^
  --http-port %HTTP_PORT% ^
  --grpc-port %GRPC_PORT% ^
  --tls-cert certs/server.crt ^
  --tls-key certs/server.key ^
  --auth-url http://127.0.0.1:%AUTH_PORT%

endlocal
