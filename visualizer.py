#!/usr/bin/env python3
"""
DocTags Zone Visualizer - Simple script to visualize zones identified in DocTags format.

Usage:
    python doctags_visualizer.py --doctags output.doctags.txt --pdf document.pdf --page 8 --output visualization.html
"""

import argparse
import os
import re
import sys
import base64
from io import BytesIO
import tempfile
from pathlib import Path
import xml.etree.ElementTree as ET
from PIL import Image, ImageDraw
import pdf2image

# Regular expression to extract location data
LOC_PATTERN = r'<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>'

def ensure_results_folder():
    """Create the results folder if it doesn't exist."""
    results_dir = Path("results")
    if not results_dir.exists():
        results_dir.mkdir()
        print(f"Created results directory: {results_dir}")
    return results_dir

def parse_arguments():
    """Parse command line arguments."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Visualize zones identified in DocTags format')
    parser.add_argument('--doctags', '-d', type=str, required=True,
                        help='Path to DocTags file')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to original PDF file')
    parser.add_argument('--page', type=int, default=8,
                        help='Page number in PDF (starts at 1, default: 8)')
    parser.add_argument('--output', '-o', type=str, default=str(results_dir / "visualization.html"),
                        help='Output HTML file path')
    parser.add_argument('--dpi', type=int, default=200,
                        help='DPI for PDF rendering')
    parser.add_argument('--show', '-s', action='store_true',
                        help='Open HTML in default browser')
    parser.add_argument('--page-count', action='store_true',
                        help='Just count pages in the PDF and exit')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='Scaling factor for zone coordinates (default: 1.0)')
    parser.add_argument('--scale-x', type=float, default=None,
                        help='X-axis scaling factor (overrides --scale)')
    parser.add_argument('--scale-y', type=float, default=None,
                        help='Y-axis scaling factor (overrides --scale)')
    parser.add_argument('--adjust', action='store_true',
                        help='Try to automatically adjust scaling')
    return parser.parse_args()

def count_pdf_pages(pdf_path):
    """Count the number of pages in a PDF file."""
    if not os.path.exists(pdf_path):
        print(f"Error: PDF file not found: {pdf_path}")
        return 0

    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(pdf_path, userpw=None, poppler_path=None)
        return info["Pages"]
    except Exception as e:
        print(f"Warning: pdfinfo failed: {e}")
        # Fallback method if pdfinfo fails
        try:
            images = pdf2image.convert_from_path(pdf_path, dpi=72, first_page=1, last_page=1)
            # Try to load the last page - increment until we get an error
            page_count = 1
            while True:
                try:
                    images = pdf2image.convert_from_path(pdf_path, dpi=72, first_page=page_count+1, last_page=page_count+1)
                    if not images:
                        break
                    page_count += 1
                except:
                    break
            return page_count
        except Exception as e2:
            print(f"Error counting PDF pages: {e2}")
            return 0

def load_image_from_pdf(pdf_path, page_num=1, dpi=200):
    """Load a specific page from PDF as an image."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    print(f"Converting PDF page {page_num} to image (DPI: {dpi})...")
    try:
        pdf_images = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=page_num,
            last_page=page_num
        )
        if not pdf_images:
            raise Exception(f"Could not extract page {page_num} from PDF")
        return pdf_images[0]  # Return the requested page
    except Exception as e:
        raise Exception(f"Error converting PDF to image: {e}")

def parse_doctags(doctags_path):
    """Parse DocTags file and extract zones with their coordinates."""
    if not os.path.exists(doctags_path):
        raise FileNotFoundError(f"DocTags file not found: {doctags_path}")

    with open(doctags_path, 'r', encoding='utf-8') as f:
        doctags_content = f.read()

    # Extract content between <doctag> tags
    doctag_pattern = r'<doctag>(.*?)</doctag>'
    doctag_match = re.search(doctag_pattern, doctags_content, re.DOTALL)

    if not doctag_match:
        raise ValueError("No <doctag> tags found in the file")

    doctag_content = doctag_match.group(1)

    # Find all tags with location information
    zones = []

    # Find all tag starts
    tag_starts = re.finditer(r'<(\w+)>', doctag_content)

    for tag_match in tag_starts:
        tag_name = tag_match.group(1)
        # Skip location tags themselves
        if tag_name.startswith('loc_'):
            continue

        # Find the end of the tag
        tag_start_pos = tag_match.start()
        tag_end_pattern = f'</({tag_name})>'
        tag_end_match = re.search(tag_end_pattern, doctag_content[tag_start_pos:])

        if not tag_end_match:
            continue  # Skip if no closing tag

        # Extract the tag content
        tag_content = doctag_content[tag_start_pos:tag_start_pos + tag_end_match.end()]

        # Look for location pattern
        loc_match = re.search(LOC_PATTERN, tag_content)

        if loc_match:
            # Extract coordinates
            x1, y1, x2, y2 = map(int, loc_match.groups())

            # Extract text content if available
            text_content = ""
            # Look for content between the location info and the closing tag
            content_pattern = f'{LOC_PATTERN}(.*?)</{tag_name}>'
            content_match = re.search(content_pattern, tag_content, re.DOTALL)

            if content_match:
                text_content = content_match.group(5).strip()

            zones.append({
                'type': tag_name,
                'x1': x1,
                'y1': y1,
                'x2': x2,
                'y2': y2,
                'content': text_content
            })

    return zones

def create_visualization(image, zones, pdf_path, page_num, total_pages, output_path):
    """Create HTML visualization with the image and overlay zones."""
    # Convert image to base64 for embedding
    buffered = BytesIO()
    image.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    # Image dimensions
    img_width, img_height = image.size

    # Define colors for different zone types
    zone_colors = {
        'section_header_level_1': '#FF5722',  # Orange
        'text': '#2196F3',                    # Blue
        'picture': '#4CAF50',                 # Green
        'table': '#9C27B0',                   # Purple
        'page_header': '#FFC107',             # Amber
        'page_footer': '#795548',             # Brown
        'default': '#607D8B'                  # Blue Grey
    }

    # Create HTML with CSS for zones
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DocTags Zone Visualization - Page {page_num}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ position: relative; display: inline-block; margin: 0 auto; background-color: white; box-shadow: 0 2px 10px rgba(0,0,0,0.2); width: {img_width}px; height: {img_height}px; }}
        .page-image {{ display: block; max-width: 100%; height: auto; }}
        .zone-overlay {{ 
            position: absolute; 
            border: 2px solid; 
            pointer-events: none;
            background-color: rgba(255, 255, 255, 0.1);
            transition: background-color 0.3s;
        }}
        .zone-overlay:hover {{ 
            background-color: rgba(255, 255, 255, 0.3);
        }}
        .zone-label {{ 
            position: absolute; 
            top: 0; 
            left: 0; 
            font-size: 12px; 
            padding: 2px 5px; 
            background-color: rgba(255, 255, 255, 0.8); 
            border-radius: 0 0 3px 0;
            max-width: 100%;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .controls {{
            margin-bottom: 10px;
            padding: 10px;
            background-color: white;
            border-radius: 3px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .legend {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 10px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            font-size: 14px;
        }}
        .legend-color {{
            width: 16px;
            height: 16px;
            margin-right: 5px;
            border: 1px solid rgba(0,0,0,0.2);
        }}
        .zone-list {{
            margin-top: 20px;
            background-color: white;
            border-radius: 3px;
            padding: 10px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }}
        .zone-item {{
            margin-bottom: 10px;
            padding-bottom: 10px;
            border-bottom: 1px solid #eee;
        }}
        .zone-type {{
            font-weight: bold;
            display: inline-block;
            padding: 2px 6px;
            border-radius: 3px;
            color: white;
            margin-bottom: 5px;
        }}
        .zone-content {{
            margin-left: 10px;
            font-size: 14px;
            color: #333;
        }}
        .pagination {{
            margin-top: 10px;
            display: flex;
            gap: 5px;
            align-items: center;
        }}
        .pagination a {{
            display: inline-block;
            padding: 5px 10px;
            background-color: #f0f0f0;
            text-decoration: none;
            color: #333;
            border-radius: 3px;
        }}
        .pagination a:hover {{
            background-color: #e0e0e0;
        }}
        .pagination .current {{
            background-color: #2196F3;
            color: white;
        }}
        .pagination-info {{
            margin-left: 10px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="controls">
        <h2>DocTags Zone Visualization - {Path(pdf_path).stem}</h2>
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <label><input type="checkbox" id="toggle-labels" checked> Show Labels</label>
                <label><input type="checkbox" id="toggle-zones" checked> Show Zones</label>
                <label><input type="checkbox" id="toggle-transparency" checked> Transparent Zones</label>
                
                <div class="legend">"""

    # Add legend items for each zone type
    zone_types = set(zone['type'] for zone in zones)
    for zone_type in zone_types:
        color = zone_colors.get(zone_type, zone_colors['default'])
        html += f"""
                    <div class="legend-item">
                        <div class="legend-color" style="background-color: {color};"></div>
                        {zone_type}
                    </div>"""

    html += """
                </div>
            </div>
            
            <div class="pagination">"""

    # Add page navigation
    if total_pages > 1:
        for p in range(1, total_pages + 1):
            if p == page_num:
                html += f"""
                <span class="current">{p}</span>"""
            else:
                # Create the filename for this page
                page_output = Path(output_path).with_stem(f"{Path(output_path).stem.split('_page_')[0]}_page_{p}")
                html += f"""
                <a href="{page_output.name}">{p}</a>"""

        html += f"""
                <span class="pagination-info">Page {page_num} of {total_pages}</span>"""

    html += """
            </div>
        </div>
    </div>

    <div class="container">
        <img src="data:image/png;base64,""" + img_base64 + """" class="page-image">
"""

    # Add zone overlays
    for i, zone in enumerate(zones):
        zone_type = zone['type']
        color = zone_colors.get(zone_type, zone_colors['default'])

        width = zone['x2'] - zone['x1']
        height = zone['y2'] - zone['y1']

        html += f"""
        <div class="zone-overlay" style="left: {zone['x1']}px; top: {zone['y1']}px; width: {width}px; height: {height}px; border-color: {color};">
            <div class="zone-label" style="border-bottom: 2px solid {color}; border-right: 2px solid {color};">
                {zone_type}
            </div>
        </div>"""

    html += """
    </div>

    <div class="zone-list">
        <h3>Detected Zones:</h3>
"""

    # Add zone details
    for zone in zones:
        zone_type = zone['type']
        color = zone_colors.get(zone_type, zone_colors['default'])

        html += f"""
        <div class="zone-item">
            <div class="zone-type" style="background-color: {color};">{zone_type}</div>
            <div class="zone-coords">Position: ({zone['x1']}, {zone['y1']}) - ({zone['x2']}, {zone['y2']})</div>
"""
        if zone['content']:
            html += f"""
            <div class="zone-content">{zone['content']}</div>
"""

        html += """
        </div>
"""

    html += """
    </div>

    <script>
        // Toggle labels visibility
        document.getElementById('toggle-labels').addEventListener('change', function() {
            var labels = document.querySelectorAll('.zone-label');
            labels.forEach(function(label) {
                label.style.display = this.checked ? 'block' : 'none';
            }, this);
        });
        
        // Toggle zones visibility
        document.getElementById('toggle-zones').addEventListener('change', function() {
            var zones = document.querySelectorAll('.zone-overlay');
            zones.forEach(function(zone) {
                zone.style.display = this.checked ? 'block' : 'none';
            }, this);
        });
        
        // Toggle zone transparency
        document.getElementById('toggle-transparency').addEventListener('change', function() {
            var zones = document.querySelectorAll('.zone-overlay');
            zones.forEach(function(zone) {
                zone.style.backgroundColor = this.checked ? 'rgba(255, 255, 255, 0.1)' : 'rgba(255, 255, 255, 0.6)';
            }, this);
        });
    </script>
</body>
</html>
"""

    # Save HTML file
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Visualization saved to: {output_path}")

    return output_path

def normalize_coordinates(zones, image_width, image_height, grid_size=500):
    """
    Normalize coordinates from the DocTags grid (0-500) to actual image dimensions.

    Args:
        zones: List of zone dictionaries with x1, y1, x2, y2 coordinates
        image_width: Width of the PDF page image in pixels
        image_height: Height of the PDF page image in pixels
        grid_size: The grid size used in DocTags (default 500)

    Returns:
        The same zones list with updated coordinates
    """
    # Create a copy of the zones to avoid modifying the original
    normalized_zones = []

    for zone in zones:
        # Clone the zone
        new_zone = zone.copy()

        # Convert from grid coordinates to actual page dimensions
        new_zone['x1'] = int(zone['x1'] * image_width / grid_size)
        new_zone['y1'] = int(zone['y1'] * image_height / grid_size)
        new_zone['x2'] = int(zone['x2'] * image_width / grid_size)
        new_zone['y2'] = int(zone['y2'] * image_height / grid_size)

        normalized_zones.append(new_zone)

    return normalized_zones

def create_debug_image(image, zones, page_num, output_path):
    """Create a debug image with rectangles around zones."""
    # Create a copy of the input image
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img)

    # Define colors for different zone types
    zone_colors = {
        'section_header_level_1': (255, 87, 34),   # Orange
        'text': (33, 150, 243),                    # Blue
        'picture': (76, 175, 80),                  # Green
        'table': (156, 39, 176),                   # Purple
        'page_header': (255, 193, 7),              # Amber
        'page_footer': (121, 85, 72),              # Brown
        'default': (96, 125, 139)                  # Blue Grey
    }

    # Draw rectangles for each zone
    for zone in zones:
        zone_type = zone['type']
        color = zone_colors.get(zone_type, zone_colors['default'])

        draw.rectangle(
            [(zone['x1'], zone['y1']), (zone['x2'], zone['y2'])],
            outline=color,
            width=2
        )

        # Add zone type label
        label_width = len(zone_type) * 7 + 6
        label_x = min(zone['x1'], image.width - label_width)  # Keep label on image

        draw.rectangle(
            [(label_x, zone['y1']), (label_x + label_width, zone['y1'] + 20)],
            fill=(255, 255, 255, 180),
            outline=color
        )
        draw.text(
            (label_x + 3, zone['y1'] + 3),
            zone_type,
            fill=color
        )

    # Draw page number on the debug image
    draw.rectangle(
        [(10, 10), (100, 40)],
        fill=(0, 0, 0, 180),
        outline=(255, 255, 255)
    )
    draw.text(
        (15, 15),
        f"Page {page_num}",
        fill=(255, 255, 255)
    )

    # Save the debug image
    debug_img.save(output_path)
    print(f"Debug image saved to: {output_path}")

    return debug_img

def process_page(pdf_path, page_num, doctags_path, output_base, dpi=200, show=False, scale=1.0, scale_x=None, scale_y=None, adjust=True):
    """Process a single page of the PDF with visualization."""
    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Generate output paths for this page
    output_name = f"{Path(output_base).stem}_page_{page_num}{Path(output_base).suffix}"
    output_path = results_dir / output_name
    debug_output = output_path.with_suffix('.debug.png')

    # Load the page image
    try:
        image = load_image_from_pdf(pdf_path, page_num, dpi)
        print(f"Page {page_num} loaded: {image.size}")
    except Exception as e:
        print(f"Error loading page {page_num}: {e}")
        return False

    # Parse DocTags
    try:
        zones = parse_doctags(doctags_path)
        print(f"Found {len(zones)} zones in DocTags")

        # Debug output to understand scaling issues
        # After parsing the zones from DocTags
        if zones:
            img_width, img_height = image.size
            print(f"Image dimensions: {img_width}x{img_height}")

            # Check if we need to normalize grid coordinates
            max_x = max([zone['x2'] for zone in zones])
            max_y = max([zone['y2'] for zone in zones])

            # If coordinates seem to be in a normalized grid (0-500 range)
            if max_x <= 500 and max_y <= 500:
                print(f"Detected normalized coordinates (0-500 grid)")
                zones = normalize_coordinates(zones, img_width, img_height)
                print(f"Applied automatic grid normalization")
            # If auto-adjust is enabled and coordinates are not in normalized grid
            elif adjust:
                width, height = image.size

                # Calculate appropriate scaling factors with better heuristics
                # Use smaller scaling to avoid cutting off content
                if max_x > 0:
                    x_scale = min(width / max_x, 1.0) if max_x > width else max(width / max_x, 0.5)
                    print(f"Auto-adjusted X scale to {x_scale:.3f} (image width: {width}, max zone x: {max_x})")
                else:
                    x_scale = 1.0

                if max_y > 0:
                    y_scale = min(height / max_y, 1.0) if max_y > height else max(height / max_y, 0.5)
                    print(f"Auto-adjusted Y scale to {y_scale:.3f} (image height: {height}, max zone y: {max_y})")
                else:
                    y_scale = 1.0

                # Apply more aggressive adjustment if image and zones are very different in scale
                if max_x > width * 5 or max_x < width / 5:
                    x_scale = width / max_x
                    print(f"Major X scale adjustment to {x_scale:.3f}")

                if max_y > height * 5 or max_y < height / 5:
                    y_scale = height / max_y
                    print(f"Major Y scale adjustment to {y_scale:.3f}")

                # Apply the scaling to all zones
                if x_scale != 1.0 or y_scale != 1.0:
                    for zone in zones:
                        zone['x1'] = int(zone['x1'] * x_scale)
                        zone['y1'] = int(zone['y1'] * y_scale)
                        zone['x2'] = int(zone['x2'] * x_scale)
                        zone['y2'] = int(zone['y2'] * y_scale)
                    print(f"Applied auto-scaling: X={x_scale}, Y={y_scale}")

    except Exception as e:
        print(f"Error parsing DocTags: {e}")
        return False

    # Get total page count
    total_pages = count_pdf_pages(pdf_path)

    # Create debug image with zones
    create_debug_image(image, zones, page_num, debug_output)

    # Create HTML visualization
    output_html = create_visualization(image, zones, pdf_path, page_num, total_pages, output_path)

    # Open in browser if requested
    if show:
        import webbrowser
        webbrowser.open(f"file:///{os.path.abspath(output_html)}")

    return True

def process_all_pages(pdf_path, doctags_path, output_base, dpi=200, show_last=False, scale=1.0, scale_x=None, scale_y=None, adjust=False):
    """Process all pages of the PDF and create visualizations."""
    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Get total page count
    total_pages = count_pdf_pages(pdf_path)
    if total_pages == 0:
        print("Error: Could not determine the number of pages in the PDF.")
        return False

    print(f"Processing all {total_pages} pages of the PDF...")

    last_html = None

    # Process each page
    for page_num in range(1, total_pages + 1):
        print(f"\nProcessing page {page_num} of {total_pages}...")

        # Generate output paths for this page
        output_name = f"{Path(output_base).stem}_page_{page_num}{Path(output_base).suffix}"
        output_path = results_dir / output_name

        # Process the page
        success = process_page(pdf_path, page_num, doctags_path, output_path, dpi, False, scale, scale_x, scale_y, adjust)

        if success:
            last_html = output_path

    # Open the last successful page in browser if requested
    if show_last and last_html:
        import webbrowser
        webbrowser.open(f"file:///{os.path.abspath(last_html)}")

    return True

def main():
    # Ensure results folder exists
    ensure_results_folder()

    # Parse arguments
    args = parse_arguments()

    # If just counting pages
    if args.page_count:
        page_count = count_pdf_pages(args.pdf)
        print(f"The PDF has {page_count} pages.")
        return

    # Check if files exist
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        return

    if not os.path.exists(args.doctags):
        print(f"Error: DocTags file not found: {args.doctags}")
        return

    # Process page(s)
    if args.page == 0:  # Special case: process all pages
        process_all_pages(
            args.pdf,
            args.doctags,
            args.output,
            args.dpi,
            args.show,
            args.scale,
            args.scale_x,
            args.scale_y,
            args.adjust
        )
    else:
        process_page(
            args.pdf,
            args.page,
            args.doctags,
            args.output,
            args.dpi,
            args.show,
            args.scale,
            args.scale_x,
            args.scale_y,
            args.adjust
        )

if __name__ == "__main__":
    main()

# --------------------------------------------------------
# Helper script to generate DocTags from a PDF
# --------------------------------------------------------

def generate_doctags_from_pdf(input_pdf, page_num, output_doctags, prompt="Convert this page to docling."):
    """
    Helper function to generate DocTags from a PDF page using the analyzer.py script.
    This is a wrapper for the original script functionality.

    Args:
        input_pdf: Path to the PDF file
        page_num: Page number to process (starting from 1)
        output_doctags: Path to save the generated DocTags
        prompt: Prompt for the model (default: "Convert this page to docling.")

    Returns:
        bool: True if successful, False otherwise
    """
    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Update output path to be in results folder
    if not isinstance(output_doctags, Path):
        output_doctags = Path(output_doctags)

    if output_doctags.parent != results_dir:
        output_doctags = results_dir / output_doctags.name

    import subprocess
    import sys

    try:
        print(f"Generating DocTags for page {page_num} of {input_pdf}...")

        # Construct command to run analyzer.py
        cmd = [
            sys.executable,  # Use the current Python interpreter
            "analyzer.py",  # Path to the script
            "--image", str(input_pdf),
            "--page", str(page_num),
            "--prompt", prompt
        ]

        # Run the command
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )

        # Check if the command was successful
        if result.returncode != 0:
            print(f"Error running analyzer.py: {result.stderr}")
            return False

        # Extract DocTags from output
        doctags_content = None
        output_lines = result.stdout.split('\n')
        in_doctags = False
        doctags_lines = []

        for line in output_lines:
            if '<doctag>' in line:
                in_doctags = True

            if in_doctags:
                doctags_lines.append(line)

            if '</doctag>' in line:
                in_doctags = False

        if not doctags_lines:
            print("No DocTags found in the output")
            return False

        # Save DocTags to file
        with open(output_doctags, 'w', encoding='utf-8') as f:
            f.write('\n'.join(doctags_lines))

        print(f"DocTags saved to: {output_doctags}")
        return True

    except Exception as e:
        print(f"Error generating DocTags: {e}")
        return False

# Command-line interface for the DocTags generator
def generate_doctags_cli():
    """Command-line interface for generating DocTags."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Generate DocTags from a PDF page')
    parser.add_argument('--pdf', type=str, required=True,
                        help='Path to PDF file')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number (starts at 1)')
    parser.add_argument('--output', type=str, default=str(results_dir / 'output.doctags.txt'),
                        help='Output DocTags file')
    parser.add_argument('--prompt', type=str, default='Convert this page to docling.',
                        help='Prompt for the model')

    args = parser.parse_args()

    # Generate DocTags
    success = generate_doctags_from_pdf(
        args.pdf,
        args.page,
        args.output,
        args.prompt
    )

    return 0 if success else 1

# Run the generator if called directly with --generate flag
if __name__ == "__main__" and '--generate' in sys.argv:
    sys.argv.remove('--generate')
    sys.exit(generate_doctags_cli())