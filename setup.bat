@echo off
REM Multi-Robot Charging Simulation Setup for Windows

echo Multi-Robot Charging Simulation Setup
echo.

REM Check if conda is available
where conda >nul 2>nul
if %errorlevel% neq 0 (
    echo Error: conda is not installed or not in PATH
    echo Please install Anaconda/Miniconda first
    pause
    exit /b 1
)

REM Check if environment exists
conda env list | findstr "multi_robot_system" >nul 2>nul
if %errorlevel% equ 0 (
    echo Conda environment 'multi_robot_system' already exists
    echo    Activating environment...
) else (
    echo Creating conda environment 'multi_robot_system'...
    call conda create -n multi_robot_system python=3.10 -y
)

REM Activate environment
echo.
echo Activating environment and installing dependencies...
call conda activate multi_robot_system

REM Install dependencies
echo.
echo Installing Python packages...
pip install -r requirements.txt

echo.
echo Setup complete!
echo.
echo To run the web interface, use: run_web.bat
echo.
pause
