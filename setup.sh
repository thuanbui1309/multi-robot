#!/bin/bash
# Setup script for Multi-Robot Charging Simulation

echo "Multi-Robot Charging Simulation Setup"
echo ""

# Check if conda is available
if ! command -v conda &> /dev/null; then
    echo "Error: conda is not installed or not in PATH"
    exit 1
fi

# Check if environment exists
if conda env list | grep -q "multi_robot_system"; then
    echo "Conda environment 'multi_robot_system' already exists"
    echo "   Activating environment..."
else
    echo "Creating conda environment 'multi_robot_system'..."
    conda create -n multi_robot_system python=3.10 -y
fi

# Activate environment
echo ""
echo "🔧 Activating environment and installing dependencies..."
eval "$(conda shell.bash hook)"
conda activate multi_robot_system

# Install dependencies
echo ""
echo "Installing Python packages..."
pip install -r requirements.txt

echo ""
echo "Setup complete!"
echo ""
echo "To run the simulation:"
echo "  ./run_web.sh    - Start web interface"
echo "  ./run_cli.sh    - Run CLI simulation"
echo ""
echo "Or manually:"
echo "  conda activate multi_robot_system"
echo "  python main.py"
echo ""
