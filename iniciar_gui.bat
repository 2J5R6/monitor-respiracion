@echo off
echo ========================================
echo   Sistema de Monitoreo Respiratorio
echo ========================================
echo.
echo Iniciando la aplicacion GUI...
echo.

:: Verificar si Python esta instalado
python --version > nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python no esta instalado o no esta en el PATH.
    echo Por favor instale Python 3.7+ y asegurese de que este en el PATH.
    echo.
    pause
    exit /b
)

:: Verificar si se instalaron las dependencias
echo Verificando dependencias...
pip install -r requirements.txt

:: Ejecutar la aplicacion
echo.
echo Ejecutando la aplicacion GUI...
echo.
python respira_gui.py

pause
