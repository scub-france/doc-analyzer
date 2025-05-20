#!/bin/bash
# analyzer_wrapper.sh - Safe wrapper for the analyzer script with proper timeouts

# This script acts as a safe wrapper around analyzer.py to ensure it doesn't get stuck

# Default timeout in seconds
TIMEOUT=120

# Function to display usage
show_usage() {
    echo "Usage: $0 [options] <pdf_path> <page_num> <output_path>"
    echo ""
    echo "Options:"
    echo "  --timeout SECONDS  Set timeout in seconds (default: 120)"
    echo "  --dpi DPI          Set DPI for PDF rendering (default: 200)"
    echo "  --help             Show this help message"
    echo ""
    echo "Example:"
    echo "  $0 --timeout 180 document.pdf 1 output.doctags.txt"
}

# Parse command-line arguments
PDF_PATH=""
PAGE_NUM=""
OUTPUT_PATH=""
DPI=200

while [[ $# -gt 0 ]]; do
    case "$1" in
        --timeout)
            TIMEOUT="$2"
            shift 2
            ;;
        --dpi)
            DPI="$2"
            shift 2
            ;;
        --help)
            show_usage
            exit 0
            ;;
        *)
            if [ -z "$PDF_PATH" ]; then
                PDF_PATH="$1"
            elif [ -z "$PAGE_NUM" ]; then
                PAGE_NUM="$1"
            elif [ -z "$OUTPUT_PATH" ]; then
                OUTPUT_PATH="$1"
            else
                echo "Error: Too many arguments"
                show_usage
                exit 1
            fi
            shift
            ;;
    esac
done

# Check if required arguments are provided
if [ -z "$PDF_PATH" ] || [ -z "$PAGE_NUM" ] || [ -z "$OUTPUT_PATH" ]; then
    echo "Error: Missing required arguments"
    show_usage
    exit 1
fi

# Check if the PDF file exists
if [ ! -f "$PDF_PATH" ]; then
    echo "Error: PDF file not found: $PDF_PATH"
    exit 1
fi

# Ensure output directory exists
OUTPUT_DIR=$(dirname "$OUTPUT_PATH")
mkdir -p "$OUTPUT_DIR"

echo "Running analyzer with timeout of $TIMEOUT seconds..."

# Use timeout command to run analyzer.py with a time limit
timeout "$TIMEOUT" python analyzer.py --image "$PDF_PATH" --page "$PAGE_NUM" --output "$OUTPUT_PATH" --dpi "$DPI"

# Check exit status
STATUS=$?
if [ $STATUS -eq 124 ] || [ $STATUS -eq 137 ]; then
    echo "Analyzer timed out after $TIMEOUT seconds"

    # Create a basic fallback doctags file
    echo "<doctag><text>Analyzer timed out after $TIMEOUT seconds</text></doctag>" > "$OUTPUT_PATH"

    # Check for any lingering python processes related to this script and kill them
    if command -v pgrep &> /dev/null; then
        PYTHON_PIDS=$(pgrep -f "python.*analyzer.py.*$PDF_PATH.*$PAGE_NUM")
        if [ -n "$PYTHON_PIDS" ]; then
            echo "Killing lingering processes: $PYTHON_PIDS"
            echo "$PYTHON_PIDS" | xargs kill -9 2>/dev/null
        fi
    fi

    exit 1
elif [ $STATUS -ne 0 ]; then
    echo "Analyzer failed with exit code $STATUS"

    # Create a basic fallback doctags file
    echo "<doctag><text>Analyzer failed with exit code $STATUS</text></doctag>" > "$OUTPUT_PATH"

    exit 1
fi

# If we get here, the analyzer was successful
echo "Analyzer completed successfully"

# Sanity check - verify the output file exists and is not empty
if [ ! -f "$OUTPUT_PATH" ] || [ ! -s "$OUTPUT_PATH" ]; then
    echo "Warning: Output file is missing or empty, creating a fallback"
    echo "<doctag><text>Analyzer did not produce valid output</text></doctag>" > "$OUTPUT_PATH"
fi

exit 0