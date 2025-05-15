#!/bin/bash
# process_single_page_fixed.sh
# This script processes a single page in a PDF document using the DocTags workflow with improved error handling

# Default values
PDF_FILE=""
PAGE=0
X_FACTOR=0.7
Y_FACTOR=0.7
DPI=200

# Function to display usage information
function show_usage {
    echo "Usage: $0 -f PDF_FILE [options]"
    echo ""
    echo "Required:"
    echo "  -f, --file FILE         Path to the PDF file"
    echo ""
    echo "Options:"
    echo "  -p, --page PAGE         Page number (if not provided, will prompt)"
    echo "  -x, --x-factor VALUE    X-axis scaling factor (default: 0.7)"
    echo "  -y, --y-factor VALUE    Y-axis scaling factor (default: 0.7)"
    echo "  -d, --dpi VALUE         DPI for PDF rendering (default: 200)"
    echo "  -h, --help              Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -f document.pdf -p 7 -x 0.8 -y 0.8"
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
        -x|--x-factor)
            X_FACTOR="$2"
            shift 2
            ;;
        -y|--y-factor)
            Y_FACTOR="$2"
            shift 2
            ;;
        -d|--dpi)
            DPI="$2"
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

# Get the PDF filename without extension
PDF_BASENAME=$(basename "$PDF_FILE" .pdf)

# If page is not specified, determine the total pages and prompt user
if [ "$PAGE" -eq 0 ]; then
    echo "Determining total number of pages..."
    # Use the visualizer's --page-count feature to get the number of pages
    TOTAL_PAGES=$(python visualizer.py --pdf "$PDF_FILE" --page-count 2>&1 | grep "The PDF has" | awk '{print $4}')

    if [ -z "$TOTAL_PAGES" ]; then
        echo "Error: Could not determine the total number of pages"
        echo "Please specify the page with -p"
        exit 1
    fi

    echo "The PDF has $TOTAL_PAGES pages."

    # Prompt for page number
    while true; do
        read -p "Enter the page number to process (1-$TOTAL_PAGES): " PAGE
        if [[ "$PAGE" =~ ^[0-9]+$ ]] && [ "$PAGE" -ge 1 ] && [ "$PAGE" -le "$TOTAL_PAGES" ]; then
            break
        else
            echo "Invalid page number. Please enter a number between 1 and $TOTAL_PAGES."
        fi
    done
fi

# Create output directory
OUTPUT_DIR="${PDF_BASENAME}_output"
mkdir -p "$OUTPUT_DIR"

# Set output filenames - explicit paths
DOCTAGS_FILE="$OUTPUT_DIR/page_${PAGE}.doctags.txt"
FIXED_DOCTAGS_FILE="$OUTPUT_DIR/page_${PAGE}.fixed.doctags.txt"
HTML_OUTPUT="$OUTPUT_DIR/page_${PAGE}.html"

echo "Processing PDF: $PDF_FILE (page $PAGE)"
echo "Scaling factors: X=$X_FACTOR, Y=$Y_FACTOR"
echo ""

# Step 1: Analyze the page
echo "Step 1: Analyzing page $PAGE..."
python analyzer.py --image "$PDF_FILE" --page "$PAGE" --output "$DOCTAGS_FILE" --dpi "$DPI"

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

# Step 2: Fix scaling issues
echo "Step 2: Fixing scaling for page $PAGE..."
python fix_scaling.py --doctags "$DOCTAGS_FILE" --output "$FIXED_DOCTAGS_FILE" --x-factor "$X_FACTOR" --y-factor "$Y_FACTOR"

if [ ! -f "$FIXED_DOCTAGS_FILE" ]; then
    echo "Warning: Failed to fix scaling for page $PAGE, using original DocTags"
    FIXED_DOCTAGS_FILE="$DOCTAGS_FILE"
fi

# Step 3: Visualize the page
echo "Step 3: Generating visualization for page $PAGE..."
python visualizer.py --doctags "$FIXED_DOCTAGS_FILE" --pdf "$PDF_FILE" --page "$PAGE" --output "$HTML_OUTPUT" --adjust --show

echo "Page $PAGE processing complete."
echo "Output saved to: $HTML_OUTPUT"

# Show the command used to process this page
echo ""
echo "Command used:"
echo "python analyzer.py --image \"$PDF_FILE\" --page $PAGE && python fix_scaling.py --doctags \"$DOCTAGS_FILE\" --output \"$FIXED_DOCTAGS_FILE\" --x-factor $X_FACTOR --y-factor $Y_FACTOR && python visualizer.py --doctags \"$FIXED_DOCTAGS_FILE\" --pdf \"$PDF_FILE\" --page $PAGE --adjust --show"

exit 0