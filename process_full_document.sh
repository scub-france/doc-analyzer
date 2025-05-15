#!/bin/bash
# process_full_document.sh
# This script processes all pages in a PDF document using the DocTags workflow

# Default values
PDF_FILE=""
START_PAGE=1
END_PAGE=0
X_FACTOR=0.7
Y_FACTOR=0.7
DPI=200
SHOW_OUTPUT=false

# Function to display usage information
function show_usage {
    echo "Usage: $0 -f PDF_FILE [options]"
    echo ""
    echo "Required:"
    echo "  -f, --file FILE         Path to the PDF file"
    echo ""
    echo "Options:"
    echo "  -s, --start PAGE        Starting page number (default: 1)"
    echo "  -e, --end PAGE          Ending page number (default: last page)"
    echo "  -x, --x-factor VALUE    X-axis scaling factor (default: 0.7)"
    echo "  -y, --y-factor VALUE    Y-axis scaling factor (default: 0.7)"
    echo "  -d, --dpi VALUE         DPI for PDF rendering (default: 200)"
    echo "  --show                  Open visualization in browser (default: false)"
    echo "  -h, --help              Display this help message"
    echo ""
    echo "Example:"
    echo "  $0 -f document.pdf -s 1 -e 10 -x 0.8 -y 0.8 --show"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        -f|--file)
            PDF_FILE="$2"
            shift 2
            ;;
        -s|--start)
            START_PAGE="$2"
            shift 2
            ;;
        -e|--end)
            END_PAGE="$2"
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
        --show)
            SHOW_OUTPUT=true
            shift
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

# If end page is not specified, get the total number of pages
if [ "$END_PAGE" -eq 0 ]; then
    echo "Determining total number of pages..."
    # Use the visualizer's --page-count feature to get the number of pages
    TOTAL_PAGES=$(python visualizer.py --pdf "$PDF_FILE" --page-count 2>&1 | grep "The PDF has" | awk '{print $4}')

    if [ -z "$TOTAL_PAGES" ]; then
        echo "Error: Could not determine the total number of pages"
        echo "Please specify the end page with -e"
        exit 1
    fi

    END_PAGE=$TOTAL_PAGES
    echo "Total pages detected: $TOTAL_PAGES"
fi

echo "Processing PDF: $PDF_FILE (pages $START_PAGE to $END_PAGE)"
echo "Scaling factors: X=$X_FACTOR, Y=$Y_FACTOR"
echo ""

# Create output directory
OUTPUT_DIR="${PDF_BASENAME}_output"
mkdir -p "$OUTPUT_DIR"

# Process each page
for ((PAGE=$START_PAGE; PAGE<=$END_PAGE; PAGE++)); do
    echo "===================================================="
    echo "Processing page $PAGE of $END_PAGE"
    echo "===================================================="

    # Set output filenames
    DOCTAGS_FILE="$OUTPUT_DIR/page_${PAGE}.doctags.txt"
    FIXED_DOCTAGS_FILE="$OUTPUT_DIR/page_${PAGE}.fixed.doctags.txt"
    HTML_OUTPUT="$OUTPUT_DIR/page_${PAGE}.html"

    # Step 1: Analyze the page
    echo "Step 1: Analyzing page $PAGE..."
    python analyzer.py --image "$PDF_FILE" --page "$PAGE" --output "$DOCTAGS_FILE" --dpi "$DPI"

    if [ ! -f "$DOCTAGS_FILE" ]; then
        echo "Warning: Failed to generate DocTags for page $PAGE, skipping to next page"
        continue
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
    SHOW_FLAG=""
    if [ "$SHOW_OUTPUT" = true ] && [ "$PAGE" -eq "$END_PAGE" ]; then
        # Only show the last page in browser to avoid opening too many windows
        SHOW_FLAG="--show"
    fi

    python visualizer.py --doctags "$FIXED_DOCTAGS_FILE" --pdf "$PDF_FILE" --page "$PAGE" --output "$HTML_OUTPUT" --adjust $SHOW_FLAG

    echo "Page $PAGE processing complete. Output saved to $HTML_OUTPUT"
    echo ""
done

echo "All pages processed successfully!"
echo "Output files are saved in: $OUTPUT_DIR"

# Open the output directory
if command -v xdg-open &> /dev/null; then
    xdg-open "$OUTPUT_DIR" &
elif command -v open &> /dev/null; then
    open "$OUTPUT_DIR" &
elif command -v explorer &> /dev/null; then
    explorer "$OUTPUT_DIR" &
fi

exit 0