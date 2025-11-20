# Run Multi-Robot Web Interface on Windows PowerShell

Write-Host "Starting Web Interface" -ForegroundColor Cyan
Write-Host ""

# Get port from argument or use default
$PORT = if ($args.Count -gt 0) { $args[0] } else { "8000" }

# Check if conda is available
if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    Write-Host "Error: conda is not installed" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "Environment: multi_robot_system" -ForegroundColor Green
Write-Host "Server will start at http://localhost:$PORT" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop" -ForegroundColor Yellow
Write-Host ""

# Run the web interface using conda run
conda run -n multi_robot_system python main.py $PORT
