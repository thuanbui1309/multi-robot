#!/bin/bash
# Run web interface in conda environment

# Activate conda environment
eval "$(conda shell.bash hook)"
conda activate multi_robot_system

# Check if activation was successful
if [ "$CONDA_DEFAULT_ENV" != "multi_robot_system" ]; then
    echo "Failed to activate multi_robot_system environment"
    echo "Please run: conda activate multi_robot_system"
    exit 1
fi

echo "Starting Web Interface"
echo "Environment: $CONDA_DEFAULT_ENV"
echo "Python: $(which python)"
echo ""
echo "Server will start at http://localhost:8000"
echo "Press Ctrl+C to stop"
echo ""

# Run the web interface (optionally pass custom port as first argument)
PORT="${1:-8000}"
python main.py "$PORT"
