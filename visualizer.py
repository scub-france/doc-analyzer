#!/usr/bin/env python3
"""
DocTags Zone Visualizer - Simple script to visualize zones identified in DocTags format.
PNG-only version: Creates debug images with rectangles around zones.

Usage:
    python visualizer_png_only.py --doctags output.doctags.txt --pdf document.pdf --page 8
"""

import argparse
import os
import re
import sys
from pathlib import Path
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

    parser = argparse.ArgumentParser(description='Visualize zones identified in DocTags format as PNG images')
    parser.add_argument('--doctags', '-d', type=str, required=True,
                        help='Path to DocTags file')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to original PDF file')
    parser.add_argument('--page', type=int, default=8,
                        help='Page number in PDF (starts at 1, default: 8)')
    parser.add_argument('--output', '-o', type=str, default=None,
                        help='Output PNG file path (default: results/visualization_page_X.png)')
    parser.add_argument('--dpi', type=int, default=200,
                        help='DPI for PDF rendering')
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

def process_page(pdf_path, page_num, doctags_path, output_path, dpi=200, scale=1.0, scale_x=None, scale_y=None, adjust=True):
    """Process a single page of the PDF with visualization."""
    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Generate output path if not provided
    if output_path is None:
        output_name = f"visualization_page_{page_num}.png"
        output_path = results_dir / output_name

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

    # Create debug image with zones
    create_debug_image(image, zones, page_num, output_path)

    return True

def process_all_pages(pdf_path, doctags_path, output_base, dpi=200, scale=1.0, scale_x=None, scale_y=None, adjust=False):
    """Process all pages of the PDF and create visualizations."""
    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Get total page count
    total_pages = count_pdf_pages(pdf_path)
    if total_pages == 0:
        print("Error: Could not determine the number of pages in the PDF.")
        return False

    print(f"Processing all {total_pages} pages of the PDF...")

    # Process each page
    for page_num in range(1, total_pages + 1):
        print(f"\nProcessing page {page_num} of {total_pages}...")

        # Generate output paths for this page
        if output_base is None:
            output_path = results_dir / f"visualization_page_{page_num}.png"
        else:
            output_path = Path(output_base).with_stem(f"{Path(output_base).stem}_page_{page_num}")

        # Process the page
        process_page(pdf_path, page_num, doctags_path, output_path, dpi, scale, scale_x, scale_y, adjust)

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
            args.scale,
            args.scale_x,
            args.scale_y,
            args.adjust
        )
    else:
        # Determine output path
        results_dir = ensure_results_folder()
        output_path = args.output if args.output else results_dir / f"visualization_page_{args.page}.png"

        process_page(
            args.pdf,
            args.page,
            args.doctags,
            output_path,
            args.dpi,
            args.scale,
            args.scale_x,
            args.scale_y,
            args.adjust
        )

if __name__ == "__main__":
    main()