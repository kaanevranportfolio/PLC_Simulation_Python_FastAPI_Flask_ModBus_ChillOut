#!/bin/bash

echo "Starting PLC Simulator..."
echo "Looking for ST programs in /app/plc_programs"

# Check if ST file exists
if [ ! -f "/app/plc_programs/hvac_control.st" ]; then
    echo "Warning: No hvac_control.st file found in /app/plc_programs"
    echo "PLC will run with empty program"
fi

# Start the PLC simulator
python main.py