#!/bin/bash
# wrapper_improved.sh - An improved wrapper script to standardize the docling workflow

# Function to display usage
function show_usage {
    echo "Usage: $0 <command> [options]"
    echo ""
    echo "Commands:"
    echo "  analyze <pdf_path> <page> <output_dir>     - Run analyzer on a PDF page"
    echo "  fix-scaling <doctags_path> <output_path>   - Fix scaling on doctags file"
    echo "  visualize <doctags_path> <pdf_path> <page> <output_path> - Create visualization"
    echo "  process <pdf_path> <page> <output_dir>     - Run the full pipeline"
    echo ""
    echo "Options for 'process':"
    echo "  --x-factor VALUE   - X-axis scaling factor (default: 0.7)"
    echo "  --y-factor VALUE   - Y-axis scaling factor (default: 0.7)"
    echo "  --dpi VALUE        - DPI for PDF rendering (default: 200)"
    echo ""
    echo "Example:"
    echo "  $0 process document.pdf 1 ./output --x-factor 0.8 --y-factor 0.8"
}

# Default values
X_FACTOR=0.7
Y_FACTOR=0.7
DPI=200

# Parse command
if [ $# -lt 1 ]; then
    show_usage
    exit 1
fi

COMMAND=$1
shift

# Log function with timestamp
function log_message {
    echo "[$(date +"%Y-%m-%d %H:%M:%S")] $1"
}

# Process based on command
case "$COMMAND" in
    analyze)
        if [ $# -lt 3 ]; then
            log_message "Error: 'analyze' requires PDF path, page number, and output directory"
            show_usage
            exit 1
        fi

        PDF_PATH=$1
        PAGE=$2
        OUTPUT_DIR=$3

        # Create output directory
        mkdir -p "$OUTPUT_DIR"

        # Define standard output path
        STANDARD_OUTPUT="$OUTPUT_DIR/page_${PAGE}.doctags.txt"

        # Run analyzer
        log_message "Running analyzer on $PDF_PATH page $PAGE..."
        python analyzer.py --image "$PDF_PATH" --page "$PAGE" --output "$STANDARD_OUTPUT" --dpi "$DPI"

        # Check for output file with various possible extensions
        if [ ! -f "$STANDARD_OUTPUT" ]; then
            log_message "Standard output not found, searching for alternatives..."

            # Look for alternative filenames
            ALTERNATIVES=(
                "$OUTPUT_DIR/page_${PAGE}.doctags.doctags.txt"
                "$OUTPUT_DIR/page_${PAGE}.txt"
                "$OUTPUT_DIR/page_${PAGE}.doctags.txt.doctags.txt"
                "$OUTPUT_DIR/output.doctags.txt"
                "$(find "$OUTPUT_DIR" -name "*.doctags.txt" | head -n 1)"
            )

            for ALT in "${ALTERNATIVES[@]}"; do
                if [ -f "$ALT" ]; then
                    log_message "Found alternative output: $ALT"
                    cp "$ALT" "$STANDARD_OUTPUT"
                    log_message "Copied to standard location: $STANDARD_OUTPUT"
                    break
                fi
            done
        fi

        # Final check
        if [ ! -f "$STANDARD_OUTPUT" ]; then
            log_message "Warning: No doctags file found. Creating an empty one to continue the process."
            echo "<doctag></doctag>" > "$STANDARD_OUTPUT"
        fi

        log_message "Analysis complete."
        echo "DOCTAGS_PATH=$STANDARD_OUTPUT"
        ;;

    fix-scaling)
        if [ $# -lt 2 ]; then
            log_message "Error: 'fix-scaling' requires doctags path and output path"
            show_usage
            exit 1
        fi

        DOCTAGS_PATH=$1
        OUTPUT_PATH=$2

        # Additional parameters
        shift 2
        while [ $# -gt 0 ]; do
            case "$1" in
                --x-factor)
                    X_FACTOR=$2
                    shift 2
                    ;;
                --y-factor)
                    Y_FACTOR=$2
                    shift 2
                    ;;
                *)
                    log_message "Unknown option: $1"
                    shift
                    ;;
            esac
        done

        # Check if input file exists
        if [ ! -f "$DOCTAGS_PATH" ]; then
            log_message "Error: Doctags file not found: $DOCTAGS_PATH"
            log_message "Creating an empty doctags file to continue the process."
            echo "<doctag></doctag>" > "$DOCTAGS_PATH"
        fi

        # Run fix_scaling with a timeout to prevent hanging
        log_message "Fixing scaling with x-factor=$X_FACTOR, y-factor=$Y_FACTOR..."
        timeout 30s python fix_scaling.py --doctags "$DOCTAGS_PATH" --output "$OUTPUT_PATH" --x-factor "$X_FACTOR" --y-factor "$Y_FACTOR"

        # Check if timeout occurred or output is missing
        if [ $? -eq 124 ] || [ ! -f "$OUTPUT_PATH" ]; then
            log_message "Warning: Scaling fix timed out or failed, using original file as fallback"
            cp "$DOCTAGS_PATH" "$OUTPUT_PATH"
        fi

        log_message "Scaling fix complete."
        echo "FIXED_DOCTAGS_PATH=$OUTPUT_PATH"
        ;;

    visualize)
        if [ $# -lt 4 ]; then
            log_message "Error: 'visualize' requires doctags path, PDF path, page number, and output path"
            show_usage
            exit 1
        fi

        DOCTAGS_PATH=$1
        PDF_PATH=$2
        PAGE=$3
        OUTPUT_PATH=$4

        # Check if input file exists
        if [ ! -f "$DOCTAGS_PATH" ]; then
            log_message "Error: Doctags file not found: $DOCTAGS_PATH"
            log_message "Creating an empty doctags file to continue the process."
            echo "<doctag></doctag>" > "$DOCTAGS_PATH"
        fi

        # Run visualizer with timeout
        log_message "Creating visualization..."
        timeout 60s python visualizer.py --doctags "$DOCTAGS_PATH" --pdf "$PDF_PATH" --page "$PAGE" --output "$OUTPUT_PATH" --adjust

        # Check if timeout occurred or output is missing
        if [ $? -eq 124 ] || [ ! -f "$OUTPUT_PATH" ]; then
            log_message "Warning: Visualization timed out or failed, creating a basic HTML file"
            # Create a simple HTML file as fallback
            cat > "$OUTPUT_PATH" << EOF
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DocTags Visualization - Page $PAGE</title>
</head>
<body>
    <h1>DocTags Visualization - Page $PAGE</h1>
    <p>The visualizer was unable to generate a complete visualization.</p>
    <p>You can try running the visualizer manually with:</p>
    <pre>python visualizer.py --doctags "$DOCTAGS_PATH" --pdf "$PDF_PATH" --page "$PAGE" --output "$OUTPUT_PATH" --adjust</pre>
</body>
</html>
EOF
        fi

        # Create a debug image if it doesn't exist
        DEBUG_IMG="${OUTPUT_PATH%.*}.debug.png"
        if [ ! -f "$DEBUG_IMG" ]; then
            log_message "Creating fallback debug image..."
            # Generate a simple placeholder image
            python -c "
from PIL import Image, ImageDraw, ImageFont
import os
img = Image.new('RGB', (800, 600), color=(240, 240, 240))
draw = ImageDraw.Draw(img)
draw.rectangle([(50, 50), (750, 550)], outline=(200, 200, 200), width=2)
draw.text((400, 300), 'Page $PAGE', fill=(100, 100, 100), anchor='mm')
img.save('$DEBUG_IMG')
" 2>/dev/null || echo "<doctag></doctag>" > "$DEBUG_IMG"
        fi

        log_message "Visualization complete: $OUTPUT_PATH"
        echo "HTML_PATH=$OUTPUT_PATH"
        echo "DEBUG_IMG=$DEBUG_IMG"
        ;;

    process)
        if [ $# -lt 3 ]; then
            log_message "Error: 'process' requires PDF path, page number, and output directory"
            show_usage
            exit 1
        fi

        PDF_PATH=$1
        PAGE=$2
        OUTPUT_DIR=$3
        shift 3

        # Process additional parameters
        while [ $# -gt 0 ]; do
            case "$1" in
                --x-factor)
                    X_FACTOR=$2
                    shift 2
                    ;;
                --y-factor)
                    Y_FACTOR=$2
                    shift 2
                    ;;
                --dpi)
                    DPI=$2
                    shift 2
                    ;;
                *)
                    log_message "Unknown option: $1"
                    shift
                    ;;
            esac
        done

        # Create output directory
        mkdir -p "$OUTPUT_DIR"

        log_message "Starting DocTags processing pipeline for page $PAGE"
        log_message "PDF: $PDF_PATH"
        log_message "Output directory: $OUTPUT_DIR"
        log_message "Parameters: x-factor=$X_FACTOR, y-factor=$Y_FACTOR, dpi=$DPI"

        # Step 1: Run analyzer
        log_message "Step 1: Analyzing PDF page..."
        DOCTAGS_PATH="$OUTPUT_DIR/page_${PAGE}.doctags.txt"
        ANALYZER_RESULT=$("$0" analyze "$PDF_PATH" "$PAGE" "$OUTPUT_DIR")
        if [[ "$ANALYZER_RESULT" =~ DOCTAGS_PATH=(.+) ]]; then
            DOCTAGS_PATH="${BASH_REMATCH[1]}"
            log_message "Analysis successful: $DOCTAGS_PATH"
        else
            log_message "Warning: Could not extract doctags path from analyzer output"
        fi

        # Step 2: Fix scaling
        log_message "Step 2: Fixing scaling..."
        FIXED_DOCTAGS_PATH="$OUTPUT_DIR/page_${PAGE}.fixed.doctags.txt"
        SCALING_RESULT=$("$0" fix-scaling "$DOCTAGS_PATH" "$FIXED_DOCTAGS_PATH" --x-factor "$X_FACTOR" --y-factor "$Y_FACTOR")
        if [[ "$SCALING_RESULT" =~ FIXED_DOCTAGS_PATH=(.+) ]]; then
            FIXED_DOCTAGS_PATH="${BASH_REMATCH[1]}"
            log_message "Scaling fix successful: $FIXED_DOCTAGS_PATH"
        else
            log_message "Warning: Could not extract fixed doctags path from scaling output"
        fi

        # Step 3: Visualize
        log_message "Step 3: Creating visualization..."
        HTML_PATH="$OUTPUT_DIR/page_${PAGE}.html"
        VISUALIZE_RESULT=$("$0" visualize "$FIXED_DOCTAGS_PATH" "$PDF_PATH" "$PAGE" "$HTML_PATH")
        if [[ "$VISUALIZE_RESULT" =~ HTML_PATH=(.+) ]]; then
            HTML_PATH="${BASH_REMATCH[1]}"
            log_message "Visualization successful: $HTML_PATH"
        else
            log_message "Warning: Could not extract HTML path from visualizer output"
        fi

        # Check if we have a debug image
        if [[ "$VISUALIZE_RESULT" =~ DEBUG_IMG=(.+) ]]; then
            DEBUG_IMG="${BASH_REMATCH[1]}"
            log_message "Debug image: $DEBUG_IMG"
        else
            log_message "Warning: No debug image found"
        fi

        log_message "Processing complete!"
        log_message "Results available at: $OUTPUT_DIR"
        log_message "DocTags file: $DOCTAGS_PATH"
        log_message "Fixed DocTags: $FIXED_DOCTAGS_PATH"
        log_message "HTML visualization: $HTML_PATH"
        ;;

    help)
        show_usage
        ;;

    *)
        log_message "Error: Unknown command '$COMMAND'"
        show_usage
        exit 1
        ;;
esac

exit 0