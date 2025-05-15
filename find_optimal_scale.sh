#!/bin/bash
# find_optimal_scale_fixed.sh
# This script helps find the optimal scaling factors for a PDF page with improved error handling

# Default values
PDF_FILE=""
PAGE=1
MIN_X=0.1
MAX_X=1.5
MIN_Y=0.1
MAX_Y=1.5
STEPS=5

# Function to display usage information
function show_usage {
    echo "Usage: $0 -f PDF_FILE [options]"
    echo ""
    echo "Required:"
    echo "  -f, --file FILE         Path to the PDF file"
    echo ""
    echo "Options:"
    echo "  -p, --page PAGE         Page number to analyze (default: 1)"
    echo "  --min-x VALUE           Minimum X scaling factor (default: 0.1)"
    echo "  --max-x VALUE           Maximum X scaling factor (default: 1.5)"
    echo "  --min-y VALUE           Minimum Y scaling factor (default: 0.1)"
    echo "  --max-y VALUE           Maximum Y scaling factor (default: 1.5)"
    echo "  --steps NUMBER          Number of steps between min and max (default: 5)"
    echo "  -h, --help              Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -f document.pdf -p 3 --min-x 0.5 --max-x 1.0 --steps 6"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)
            PDF_FILE="$2"
            shift 2
            ;;
        -p|--page)
            PAGE="$2"
            shift 2
            ;;
        --min-x)
            MIN_X="$2"
            shift 2
            ;;
        --max-x)
            MAX_X="$2"
            shift 2
            ;;
        --min-y)
            MIN_Y="$2"
            shift 2
            ;;
        --max-y)
            MAX_Y="$2"
            shift 2
            ;;
        --steps)
            STEPS="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Error: Unknown option $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if PDF file is provided
if [ -z "$PDF_FILE" ]; then
    echo "Error: PDF file is required"
    show_usage
    exit 1
fi

# Check if PDF file exists
if [ ! -f "$PDF_FILE" ]; then
    echo "Error: PDF file '$PDF_FILE' not found"
    exit 1
fi

# Get PDF basename for output files
PDF_BASENAME=$(basename "$PDF_FILE" .pdf)
OUTPUT_DIR="${PDF_BASENAME}_scale_test"
mkdir -p "$OUTPUT_DIR"

# Step 1: Run analyzer once to get the DocTags
echo "Step 1: Analyzing page $PAGE to generate DocTags..."
DOCTAGS_FILE="$OUTPUT_DIR/page_${PAGE}.doctags.txt"
python analyzer.py --image "$PDF_FILE" --page "$PAGE" --output "$DOCTAGS_FILE"

# Check for DocTags file with different extensions
if [ ! -f "$DOCTAGS_FILE" ]; then
    # Try alternative extensions
    ALTERNATIVE_FILE="$OUTPUT_DIR/page_${PAGE}.doctags.doctags.txt"
    if [ -f "$ALTERNATIVE_FILE" ]; then
        echo "Found DocTags at alternative location: $ALTERNATIVE_FILE"
        DOCTAGS_FILE="$ALTERNATIVE_FILE"
    else
        # Try to find any doctags file in the output directory
        FOUND_FILE=$(find "$OUTPUT_DIR" -name "*.doctags.txt" -print -quit)
        if [ -n "$FOUND_FILE" ]; then
            echo "Found DocTags at location: $FOUND_FILE"
            DOCTAGS_FILE="$FOUND_FILE"
        else
            echo "Error: Failed to generate DocTags for page $PAGE"
            echo "Could not find any doctags files in $OUTPUT_DIR"
            exit 1
        fi
    fi
fi

echo "Using DocTags file: $DOCTAGS_FILE"

# Create HTML index to easily compare results
INDEX_FILE="$OUTPUT_DIR/index.html"
echo "<!DOCTYPE html>
<html>
<head>
    <meta charset='UTF-8'>
    <title>Scale Factor Test - Page $PAGE</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
        .card { border: 1px solid #ccc; border-radius: 5px; padding: 10px; }
        .card h3 { margin-top: 0; text-align: center; }
        .card img { max-width: 100%; border: 1px solid #eee; }
        .card a { display: block; text-align: center; margin-top: 10px; }
    </style>
</head>
<body>
    <h1>Scale Factor Test - Page $PAGE of $PDF_BASENAME.pdf</h1>
    <p>Click on any thumbnail to open the full visualization.</p>
    <div class='grid'>" > "$INDEX_FILE"

# Step 2: Try different combinations of scaling factors
echo "Step 2: Testing different scaling factors..."

# Calculate step sizes
X_STEP=$(echo "scale=6; ($MAX_X - $MIN_X) / $STEPS" | bc)
Y_STEP=$(echo "scale=6; ($MAX_Y - $MIN_Y) / $STEPS" | bc)

for i in $(seq 0 $STEPS); do
    X_FACTOR=$(echo "scale=2; $MIN_X + ($i * $X_STEP)" | bc)

    for j in $(seq 0 $STEPS); do
        Y_FACTOR=$(echo "scale=2; $MIN_Y + ($j * $Y_STEP)" | bc)

        echo "Testing X=$X_FACTOR, Y=$Y_FACTOR"

        # Generate fixed DocTags
        FIXED_DOCTAGS="$OUTPUT_DIR/page_${PAGE}_x${X_FACTOR}_y${Y_FACTOR}.doctags.txt"
        python fix_scaling.py --doctags "$DOCTAGS_FILE" --output "$FIXED_DOCTAGS" --x-factor "$X_FACTOR" --y-factor "$Y_FACTOR" > /dev/null

        # Generate visualization
        HTML_OUTPUT="$OUTPUT_DIR/page_${PAGE}_x${X_FACTOR}_y${Y_FACTOR}.html"
        python visualizer.py --doctags "$FIXED_DOCTAGS" --pdf "$PDF_FILE" --page "$PAGE" --output "$HTML_OUTPUT" --adjust > /dev/null

        # Generate debug image for thumbnail
        DEBUG_IMG="$OUTPUT_DIR/page_${PAGE}_x${X_FACTOR}_y${Y_FACTOR}.debug.png"

        # Check if the debug image exists
        if [ ! -f "$DEBUG_IMG" ]; then
            echo "Warning: Debug image not found, trying alternative name..."
            ALT_DEBUG_IMG=$(find "$OUTPUT_DIR" -name "page_${PAGE}_x${X_FACTOR}_y${Y_FACTOR}*.png" -print -quit)
            if [ -n "$ALT_DEBUG_IMG" ]; then
                DEBUG_IMG="$ALT_DEBUG_IMG"
            fi
        fi

        # Add to index only if files exist
        if [ -f "$HTML_OUTPUT" ] && [ -f "$DEBUG_IMG" ]; then
            echo "        <div class='card'>
            <h3>X=$X_FACTOR, Y=$Y_FACTOR</h3>
            <a href='$(basename "$HTML_OUTPUT")'>
                <img src='$(basename "$DEBUG_IMG")' alt='X=$X_FACTOR, Y=$Y_FACTOR'>
            </a>
            <a href='$(basename "$HTML_OUTPUT")'>Open Visualization</a>
        </div>" >> "$INDEX_FILE"
        else
            echo "Warning: Skipping this combination as files not created successfully."
        fi
    done
done

# Finish HTML index
echo "    </div>
</body>
</html>" >> "$INDEX_FILE"

echo "
Scale factor testing complete!
Open $INDEX_FILE in a web browser to compare results.
"

# Try to open the index file in a browser
if command -v xdg-open &> /dev/null; then
    xdg-open "$INDEX_FILE" &
elif command -v open &> /dev/null; then
    open "$INDEX_FILE" &
elif command -v explorer &> /dev/null; then
    explorer "$INDEX_FILE" &
fi

exit 0
