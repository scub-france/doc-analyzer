#!/usr/bin/env python3
"""
DocTags Zone Visualizer - Visualize zones identified in DocTags format.
"""

import argparse
import os
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

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

    # Define all possible tag types to look for
    tag_types = [
        'section_header_level_1', 'section_header_level_2', 'section_header_level_3',
        'text', 'picture', 'table', 'page_header', 'page_footer',
        'title', 'author', 'abstract', 'keywords', 'paragraph',
        'list_item', 'code_block', 'footnote', 'caption'
    ]

    # Find all zones with location information using a more robust pattern
    for tag_type in tag_types:
        # Pattern to match the complete tag with location data
        pattern = rf'<{tag_type}>.*?{LOC_PATTERN}.*?</{tag_type}>'
        matches = re.finditer(pattern, doctag_content, re.DOTALL)

        for match in matches:
            full_match = match.group(0)
            loc_match = re.search(LOC_PATTERN, full_match)

            if loc_match:
                x1, y1, x2, y2 = map(int, loc_match.groups())

                # Extract text content (remove location tags)
                content_start = full_match.find('>') + 1
                content_end = full_match.rfind('</')
                content = full_match[content_start:content_end]
                content = re.sub(r'<loc_\d+>', '', content).strip()

                zones.append({
                    'type': tag_type,
                    'x1': x1, 'y1': y1,
                    'x2': x2, 'y2': y2,
                    'content': content
                })

    # Also try a more general pattern for any tags we might have missed
    general_pattern = r'<(\w+)>.*?' + LOC_PATTERN + r'.*?</\1>'
    general_matches = re.finditer(general_pattern, doctag_content, re.DOTALL)

    found_tags = set()
    for zone in zones:
        found_tags.add(f"{zone['type']}_{zone['x1']}_{zone['y1']}")

    for match in general_matches:
        tag_name = match.group(1)
        if tag_name.startswith('loc_'):
            continue

        x1, y1, x2, y2 = map(int, match.groups()[1:5])
        tag_key = f"{tag_name}_{x1}_{y1}"

        # Avoid duplicates
        if tag_key not in found_tags:
            full_match = match.group(0)
            content_start = full_match.find('>') + 1
            content_end = full_match.rfind('</')
            content = full_match[content_start:content_end]
            content = re.sub(r'<loc_\d+>', '', content).strip()

            zones.append({
                'type': tag_name,
                'x1': x1, 'y1': y1,
                'x2': x2, 'y2': y2,
                'content': content
            })
            found_tags.add(tag_key)

    # If no zones found, log the content for debugging
    if not zones:
        print(f"Warning: No zones with location data found in {doctags_path}")
        print(f"DocTags content preview: {doctag_content[:500]}...")

        # Try to find any loc_ tags to debug
        loc_tags = re.findall(r'<loc_\d+>', doctag_content)
        if loc_tags:
            print(f"Found {len(loc_tags)} location tags in the file")
        else:
            print("No location tags found in the file at all")

    # Sort zones by position (top to bottom, left to right)
    zones.sort(key=lambda z: (z['y1'], z['x1']))

    print(f"Parsed {len(zones)} zones from DocTags")
    for zone in zones[:5]:  # Show first 5 zones for debugging
        print(f"  - {zone['type']}: ({zone['x1']},{zone['y1']})-({zone['x2']},{zone['y2']})")

    return zones

def create_visualization(image, zones, page_num, output_path):
    """Create a visualization image with rectangles around zones."""
    debug_img = image.copy()
    draw = ImageDraw.Draw(debug_img, mode='RGBA')  # Use RGBA mode for transparency

    print(f"Creating visualization with {len(zones)} zones")

    # Try to use a default font, fallback to PIL default if not available
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        try:
            # Try macOS font locations
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        except:
            try:
                # Try Windows font locations
                font = ImageFont.truetype("C:\\Windows\\Fonts\\Arial.ttf", 14)
            except:
                font = ImageFont.load_default()

    # Draw rectangles for each zone
    zone_count = 0
    for zone in zones:
        zone_type = zone['type']
        color = ZONE_COLORS.get(zone_type, ZONE_COLORS['default'])

        # Ensure coordinates are integers
        x1, y1 = int(zone['x1']), int(zone['y1'])
        x2, y2 = int(zone['x2']), int(zone['y2'])

        # Skip invalid zones
        if x1 >= x2 or y1 >= y2:
            print(f"Skipping invalid zone {zone_type}: ({x1},{y1})-({x2},{y2})")
            continue

        # Ensure coordinates are within image bounds
        x1 = max(0, min(x1, image.width - 1))
        y1 = max(0, min(y1, image.height - 1))
        x2 = max(0, min(x2, image.width))
        y2 = max(0, min(y2, image.height))

        print(f"Drawing {zone_type} at ({x1},{y1})-({x2},{y2}) with color {color}")

        # Draw rectangle with thicker line
        draw.rectangle(
            [(x1, y1), (x2, y2)],
            outline=color,
            width=3  # Increased from 2 to make more visible
        )

        # Draw corners for better visibility
        corner_length = 10
        corner_width = 4
        # Top-left corner
        draw.line([(x1, y1), (x1 + corner_length, y1)], fill=color, width=corner_width)
        draw.line([(x1, y1), (x1, y1 + corner_length)], fill=color, width=corner_width)
        # Top-right corner
        draw.line([(x2 - corner_length, y1), (x2, y1)], fill=color, width=corner_width)
        draw.line([(x2, y1), (x2, y1 + corner_length)], fill=color, width=corner_width)
        # Bottom-left corner
        draw.line([(x1, y2 - corner_length), (x1, y2)], fill=color, width=corner_width)
        draw.line([(x1, y2), (x1 + corner_length, y2)], fill=color, width=corner_width)
        # Bottom-right corner
        draw.line([(x2 - corner_length, y2), (x2, y2)], fill=color, width=corner_width)
        draw.line([(x2, y2 - corner_length), (x2, y2)], fill=color, width=corner_width)

        # Add zone type label with better visibility
        label_text = zone_type.replace('_', ' ').title()

        # Get text size
        text_bbox = draw.textbbox((0, 0), label_text, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]

        # Position label
        label_x = min(x1 + 2, image.width - text_width - 4)
        label_y = max(y1 - text_height - 4, 2)

        # Draw label background
        draw.rectangle(
            [(label_x - 2, label_y - 2),
             (label_x + text_width + 2, label_y + text_height + 2)],
            fill=(255, 255, 255, 200),
            outline=color,
            width=2
        )

        # Draw label text
        draw.text(
            (label_x, label_y),
            label_text,
            fill=color,
            font=font
        )

        zone_count += 1

    print(f"Drew {zone_count} zones on the image")

    # Draw page number with better visibility
    page_text = f"Page {page_num}"
    page_bbox = draw.textbbox((0, 0), page_text, font=font)
    page_width = page_bbox[2] - page_bbox[0]
    page_height = page_bbox[3] - page_bbox[1]

    draw.rectangle(
        [(10, 10), (20 + page_width, 20 + page_height)],
        fill=(0, 0, 0, 200),
        outline=(255, 255, 255)
    )
    draw.text(
        (15, 15),
        page_text,
        fill=(255, 255, 255),
        font=font
    )

    # Save the image
    debug_img.save(output_path, format="PNG")
    print(f"Visualization saved to: {output_path}")
    print(f"Output image size: {debug_img.size}")

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
            # Debug: print coordinate ranges
            x_coords = [zone['x1'] for zone in zones] + [zone['x2'] for zone in zones]
            y_coords = [zone['y1'] for zone in zones] + [zone['y2'] for zone in zones]
            print(f"Coordinate ranges: X({min(x_coords)}-{max(x_coords)}), Y({min(y_coords)}-{max(y_coords)})")
            print(f"Image dimensions: {image.width}x{image.height}")

            # Check if we need to adjust coordinates
            max_x = max([zone['x2'] for zone in zones])
            max_y = max([zone['y2'] for zone in zones])

            # Auto-adjust if needed
            if max_x <= DEFAULT_GRID_SIZE and max_y <= DEFAULT_GRID_SIZE:
                print(f"Detected normalized coordinates (0-{DEFAULT_GRID_SIZE} grid)")
                zones = normalize_coordinates(zones, image.width, image.height)
                print(f"After normalization - X range: {min([z['x1'] for z in zones])}-{max([z['x2'] for z in zones])}")
            elif adjust:
                print(f"Applying auto-adjustment (max coords: {max_x}, {max_y})")
                zones = auto_adjust_coordinates(zones, image.width, image.height)
                print(f"After adjustment - X range: {min([z['x1'] for z in zones])}-{max([z['x2'] for z in zones])}")
            else:
                print("No coordinate adjustment applied")

            # Verify coordinates are within image bounds
            out_of_bounds = 0
            for zone in zones:
                if (zone['x2'] > image.width or zone['y2'] > image.height or
                        zone['x1'] < 0 or zone['y1'] < 0):
                    out_of_bounds += 1
                    print(f"Warning: Zone {zone['type']} has out-of-bounds coordinates: "
                          f"({zone['x1']},{zone['y1']})-({zone['x2']},{zone['y2']})")

            if out_of_bounds > 0:
                print(f"Warning: {out_of_bounds} zones have coordinates outside image bounds!")

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