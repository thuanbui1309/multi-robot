# Multi-Robot Charging Simulation Setup for Windows PowerShell

Write-Host "Multi-Robot Charging Simulation Setup" -ForegroundColor Cyan
Write-Host ""

# Check if conda is available
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "Error: conda is not installed or not in PATH" -ForegroundColor Red
    Write-Host "Please install Anaconda/Miniconda first"
    Read-Host "Press Enter to exit"
    exit 1
}

# Check if environment exists
$envExists = conda env list | Select-String "multi_robot_system"
if ($envExists) {
    Write-Host "Conda environment 'multi_robot_system' already exists" -ForegroundColor Yellow
    Write-Host "   Activating environment..."
} else {
    Write-Host "Creating conda environment 'multi_robot_system'..." -ForegroundColor Green
    conda create -n multi_robot_system python=3.10 -y
}

# Install dependencies
Write-Host ""
Write-Host "Installing Python packages..." -ForegroundColor Green
conda run -n multi_robot_system pip install -r requirements.txt

Write-Host ""
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "To run the web interface, use: .\run_web.ps1" -ForegroundColor Cyan
Write-Host "Or in Command Prompt, use: run_web.bat" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
