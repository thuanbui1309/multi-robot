@echo off
REM Run Multi-Robot Web Interface on Windows

REM Activate conda environment
call conda activate multi_robot_system

REM Check if activation was successful
if "%CONDA_DEFAULT_ENV%" neq "multi_robot_system" (
    echo Failed to activate multi_robot_system environment
    echo Please run setup.bat first or manually activate:
    echo    conda activate multi_robot_system
    pause
    exit /b 1
)

echo Starting Web Interface
echo Environment: %CONDA_DEFAULT_ENV%
echo Python: 
where python
echo.
echo Server will start at http://localhost:8000
echo Press Ctrl+C to stop
echo.

REM Run the web interface
set PORT=%1
if "%PORT%"=="" set PORT=8000
python main.py %PORT%
