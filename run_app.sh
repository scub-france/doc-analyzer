#!/bin/bash

echo "Starting DocTags Application..."

# Check if backend directory exists
if [ ! -d "backend" ]; then
    echo "Error: backend directory not found!"
    echo "Please run the reorganization script first."
    exit 1
fi

# Check if app.py exists in backend
if [ ! -f "backend/app.py" ]; then
    echo "Error: backend/app.py not found!"
    exit 1
fi

# Run the Flask application
echo "Running Flask application..."
python backend/app.py