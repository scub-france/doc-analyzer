#!/usr/bin/env python3
"""
DocTags Zone Visualizer - Visualize zones identified in DocTags format.
"""

import argparse
import os
import re
from pathlib import Path
from PIL import Image, ImageDraw

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.utils import (ensure_results_folder, load_pdf_page, count_pdf_pages,
                           normalize_coordinates, auto_adjust_coordinates)
from backend.config import ZONE_COLORS, DEFAULT_DPI, DEFAULT_GRID_SIZE

# Regular expression to extract location data
LOC_PATTERN = r'<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>'

def parse_arguments():
    """Parse command line arguments."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Visualize zones identified in DocTags format')
    parser.add_argument('--doctags', '-d', type=str, required=False,
                        help='Path to DocTags file (optional, will auto-detect if not provided)')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to original PDF file')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number in PDF (starts at 1)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output PNG file path')
    parser.add_argument('--dpi', type=int, default=DEFAULT_DPI,
                        help='DPI for PDF rendering')
    parser.add_argument('--adjust', action='store_true',
                        help='Try to automatically adjust scaling')
    return parser.parse_args()

def parse_doctags(doctags_path):
    """Parse DocTags file and extract zones with their coordinates."""
    if not os.path.exists(doctags_path):
        raise FileNotFoundError(f"DocTags file not found: {doctags_path}")

    with open(doctags_path, 'r', encoding='utf-8') as f:
        doctags_content = f.read()

    # Check if file is empty or invalid
    if not doctags_content.strip():
        raise ValueError("DocTags file is empty")

    # Extract content between <doctag> tags
    doctag_match = re.search(r'<doctag>(.*?)</doctag>', doctags_content, re.DOTALL)
    if not doctag_match:
        raise ValueError("No <doctag> tags found in the file")

    doctag_content = doctag_match.group(1)
    zones = []

    # Find all tags with location information
    tag_starts = re.finditer(r'<(\w+)>', doctag_content)

    for tag_match in tag_starts:
        tag_name = tag_match.group(1)
        if tag_name.startswith('loc_'):
            continue

        tag_start_pos = tag_match.start()
        tag_end_pattern = f'</({tag_name})>'
        tag_end_match = re.search(tag_end_pattern, doctag_content[tag_start_pos:])

        if not tag_end_match:
            continue

        tag_content = doctag_content[tag_start_pos:tag_start_pos + tag_end_match.end()]
        loc_match = re.search(LOC_PATTERN, tag_content)

        if loc_match:
            x1, y1, x2, y2 = map(int, loc_match.groups())

            # Extract text content
            content_pattern = f'{LOC_PATTERN}(.*?)</{tag_name}>'
            content_match = re.search(content_pattern, tag_content, re.DOTALL)
            text_content = content_match.group(5).strip() if content_match else ""

            zones.append({
                'type': tag_name,
                'x1': x1, 'y1': y1,
                'x2': x2, 'y2': y2,
                'content': text_content
            })

    # If no zones found, it might be a page with no detectable content
    if not zones:
        print(f"Warning: No zones with location data found in {doctags_path}")

    return zones

def create_visualization(image, zones, page_num, output_path):
    """Create a visualization image with rectangles around zones."""
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img)

    # Draw rectangles for each zone
    for zone in zones:
        zone_type = zone['type']
        color = ZONE_COLORS.get(zone_type, ZONE_COLORS['default'])

        # Draw rectangle
        draw.rectangle(
            [(zone['x1'], zone['y1']), (zone['x2'], zone['y2'])],
            outline=color,
            width=2
        )

        # Add zone type label
        label_width = len(zone_type) * 7 + 6
        label_x = min(zone['x1'], image.width - label_width)

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

    # Draw page number
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

    # Save the image
    debug_img.save(output_path)
    print(f"Visualization saved to: {output_path}")

    return debug_img

def process_page(pdf_path, page_num, doctags_path, output_path, dpi, adjust):
    """Process a single page of the PDF with visualization."""
    results_dir = ensure_results_folder()

    if output_path is None:
        output_path = results_dir / f"visualization_page_{page_num}.png"
    else:
        output_path = Path(output_path)

    # Load the page image
    image = load_pdf_page(pdf_path, page_num, dpi)
    print(f"Page {page_num} loaded: {image.size}")

    try:
        # Parse DocTags
        zones = parse_doctags(doctags_path)
        print(f"Found {len(zones)} zones in DocTags")

        if zones:
            # Check if we need to adjust coordinates
            max_x = max([zone['x2'] for zone in zones])
            max_y = max([zone['y2'] for zone in zones])

            # Auto-adjust if needed
            if max_x <= DEFAULT_GRID_SIZE and max_y <= DEFAULT_GRID_SIZE:
                print(f"Detected normalized coordinates (0-{DEFAULT_GRID_SIZE} grid)")
                zones = normalize_coordinates(zones, image.width, image.height)
            elif adjust:
                zones = auto_adjust_coordinates(zones, image.width, image.height)
        else:
            print(f"Warning: No zones found for page {page_num}, creating blank visualization")

    except ValueError as e:
        print(f"Warning: {e} for page {page_num}, creating blank visualization")
        zones = []

    # Create visualization (even if no zones)
    create_visualization(image, zones, page_num, output_path)

    return True

def main():
    args = parse_arguments()

    # Check if files exist
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        return

    if not os.path.exists(args.doctags):
        print(f"Error: DocTags file not found: {args.doctags}")
        return

    # Process the page
    process_page(
        args.pdf,
        args.page,
        args.doctags,
        args.output,
        args.dpi,
        args.adjust
    )

if __name__ == "__main__":
    main()