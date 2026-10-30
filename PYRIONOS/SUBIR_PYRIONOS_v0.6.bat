@echo off
setlocal EnableExtensions
set "REPO=https://github.com/mobatfb/archmoba-dev.git"
set "EXPECTED_SHA=582f4eb432eb2d4f70fdb67a0d9396b3935e4b17c4327e1417722df90e66af0a"
set "ISO=%~dp0PYRION_OS_v0.6.iso"
set "WORK=%TEMP%\PYRIONOS-upload-%RANDOM%-%RANDOM%"

echo ===========================================
echo   PYRION OS v0.6 - Publicar ISO en GitHub
echo ===========================================
echo.
if not exist "%ISO%" (
  echo ERROR: No se encontro PYRION_OS_v0.6.iso
  echo Coloca esta herramienta BAT junto al archivo ISO original.
  goto :error
)
where git >nul 2>nul
if errorlevel 1 (
  echo ERROR: No se encontro Git para Windows.
  echo Instala Git, inicia sesion en GitHub y ejecuta de nuevo.
  goto :error
)

echo Comprobando integridad SHA-256...
set "FILE_HASH="
for /f "usebackq delims=" %%H in (`powershell -NoProfile -Command "(Get-FileHash -LiteralPath $env:ISO -Algorithm SHA256).Hash.ToLowerInvariant()"`) do set "FILE_HASH=%%H"
if /I not "%FILE_HASH%"=="%EXPECTED_SHA%" (
  echo ERROR: El ISO no coincide con el archivo verificado.
  echo SHA-256 obtenido: %FILE_HASH%
  echo SHA-256 esperado: %EXPECTED_SHA%
  goto :error
)
echo Integridad OK.

echo.
echo Descargando la rama main del repositorio...
git clone --depth 1 --branch main "%REPO%" "%WORK%"
if errorlevel 1 goto :error
if not exist "%WORK%\PYRIONOS" mkdir "%WORK%\PYRIONOS"
copy /b /y "%ISO%" "%WORK%\PYRIONOS\PYRION_OS_v0.6.iso" >nul
if errorlevel 1 goto :error

echo.
echo Creando commit...
git -C "%WORK%" add -- PYRIONOS/PYRION_OS_v0.6.iso
if errorlevel 1 goto :error
git -C "%WORK%" diff --cached --quiet
if not errorlevel 1 (
  echo La ISO ya estaba subida: no hay cambios nuevos.
  goto :success
)
git -C "%WORK%" commit -m "PYRIONOS: publicar ISO PYRION OS v0.6"
if errorlevel 1 (
  echo ERROR: Git no pudo crear el commit.
  echo Comprueba git config --global user.name y user.email.
  goto :error
)
echo.
echo Subiendo 88 MiB a GitHub. Necesitas permisos de escritura.
git -C "%WORK%" push origin main
if errorlevel 1 (
  echo ERROR: No se pudo subir a GitHub.
  echo Comprueba la autenticacion y tu permiso de escritura.
  echo Copia temporal conservada: %WORK%
  goto :error
)
:success
echo.
echo PUBLICACION CONFIRMADA EN GITHUB.
echo https://github.com/mobatfb/archmoba-dev/tree/main/PYRIONOS
start "" "https://github.com/mobatfb/archmoba-dev/tree/main/PYRIONOS"
if exist "%WORK%" rmdir /s /q "%WORK%"
pause
exit /b 0
:error
echo.
echo La subida no ha sido confirmada.
pause
exit /b 1
