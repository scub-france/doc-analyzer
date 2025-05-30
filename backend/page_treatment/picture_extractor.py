#!/usr/bin/env python3
"""
DocTags Picture Extractor - Extract <picture> elements from DocTags.
"""

import argparse
import os
import re
from pathlib import Path
from PIL import Image

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.utils import (ensure_results_folder, load_pdf_page,
                           normalize_coordinates, auto_adjust_coordinates,
                           validate_coordinates)
from backend.config import DEFAULT_DPI, MAX_IMAGE_WIDTH, DEFAULT_GRID_SIZE

# Regular expression to extract picture location data
PICTURE_PATTERN = r'<picture>.*?<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>(.*?)</picture>'

def parse_arguments():
    """Parse command line arguments."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Extract pictures from DocTags format')
    parser.add_argument('--doctags', '-d', type=str, required=True,
                        help='Path to DocTags file')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to original PDF file')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number in PDF (starts at 1)')
    parser.add_argument('--output', '-o', type=str, default=str(results_dir / "pictures"),
                        help='Output directory for extracted pictures')
    parser.add_argument('--dpi', type=int, default=DEFAULT_DPI,
                        help='DPI for PDF rendering')
    parser.add_argument('--max-width', type=int, default=MAX_IMAGE_WIDTH,
                        help='Maximum width of output images in pixels')
    parser.add_argument('--adjust', action='store_true',
                        help='Try to automatically adjust scaling')
    parser.add_argument('--margin', type=int, default=0,
                        help='Add margin around extracted pictures in pixels')
    return parser.parse_args()

def extract_pictures_from_doctags(doctags_path):
    """Parse DocTags file and extract picture elements with their coordinates."""
    if not os.path.exists(doctags_path):
        raise FileNotFoundError(f"DocTags file not found: {doctags_path}")

    with open(doctags_path, 'r', encoding='utf-8') as f:
        doctags_content = f.read()

    pictures = []
    picture_matches = re.finditer(PICTURE_PATTERN, doctags_content, re.DOTALL)

    for i, match in enumerate(picture_matches):
        x1, y1, x2, y2, caption = match.groups()

        # Clean caption
        clean_caption = re.sub(r'<loc_\d+>', '', caption).strip()

        pictures.append({
            'id': i + 1,
            'x1': int(x1), 'y1': int(y1),
            'x2': int(x2), 'y2': int(y2),
            'caption': clean_caption
        })

    return pictures

def extract_and_save_pictures(image, pictures, output_dir, max_width, margin):
    """Extract picture regions from the image and save them as separate files."""
    output_path = ensure_results_folder(output_dir)
    saved_files = []

    for picture in pictures:
        try:
            # Add margin to coordinates
            x1 = max(0, picture['x1'] - margin)
            y1 = max(0, picture['y1'] - margin)
            x2 = min(image.width, picture['x2'] + margin)
            y2 = min(image.height, picture['y2'] + margin)

            # Validate coordinates
            if not validate_coordinates(x1, y1, x2, y2, image.width, image.height):
                print(f"Warning: Invalid coordinates for picture {picture['id']}")
                continue

            # Crop the image
            cropped_img = image.crop((x1, y1, x2, y2))

            # Resize if necessary
            if cropped_img.width > max_width:
                ratio = max_width / cropped_img.width
                new_height = int(cropped_img.height * ratio)
                cropped_img = cropped_img.resize((max_width, new_height), Image.LANCZOS)

            # Generate filename
            if picture['caption']:
                safe_caption = re.sub(r'[^\w\s-]', '', picture['caption'])[:30].strip().replace(' ', '_').lower()
                filename = f"picture_{picture['id']}_{safe_caption}.png"
            else:
                filename = f"picture_{picture['id']}.png"

            # Save the image
            output_file = output_path / filename
            cropped_img.save(output_file, format="PNG")

            # Save caption if available
            if picture['caption']:
                caption_file = output_path / f"{output_file.stem}.txt"
                with open(caption_file, 'w', encoding='utf-8') as f:
                    f.write(picture['caption'])

            print(f"Saved picture {picture['id']} to {output_file}")
            saved_files.append(output_file)

        except Exception as e:
            print(f"Error processing picture {picture['id']}: {e}")

    return saved_files

def create_html_index(pictures, saved_files, pdf_name, page_num, output_dir):
    """Create an HTML index file of all extracted pictures."""
    output_path = Path(output_dir)
    index_file = output_path / "index.html"

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Extracted Pictures from {pdf_name} - Page {page_num}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        h1 {{ color: #333; }}
        .gallery {{ 
            display: grid; 
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 20px;
            margin-top: 20px;
        }}
        .picture-card {{ 
            background-color: white;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            overflow: hidden;
        }}
        .picture-card img {{ 
            width: 100%;
            height: auto;
            display: block;
        }}
        .picture-info {{ 
            padding: 15px;
        }}
        .no-pictures {{ 
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            text-align: center;
            color: #777;
        }}
    </style>
</head>
<body>
    <h1>Extracted Pictures from {pdf_name} - Page {page_num}</h1>
    <p>Total pictures found: {len(pictures)}</p>
"""

    if pictures:
        html += '    <div class="gallery">\n'

        for picture, file_path in zip(pictures, saved_files):
            rel_path = file_path.name
            html += f"""        <div class="picture-card">
            <img src="{rel_path}" alt="Picture {picture['id']}">
            <div class="picture-info">
                <h3>Picture {picture['id']}</h3>
                {f'<div class="picture-caption">{picture["caption"]}</div>' if picture['caption'] else ''}
                <div class="picture-coords">Coordinates: ({picture['x1']},{picture['y1']})-({picture['x2']},{picture['y2']})</div>
            </div>
        </div>
"""

        html += '    </div>\n'
    else:
        html += '    <div class="no-pictures">\n        <h2>No pictures found on this page</h2>\n    </div>\n'

    html += '</body>\n</html>\n'

    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Created index file: {index_file}")
    return index_file

def main():
    args = parse_arguments()
    output_dir = ensure_results_folder(args.output)

    try:
        # Extract pictures from DocTags
        print(f"Extracting pictures from {args.doctags}...")
        pictures = extract_pictures_from_doctags(args.doctags)

        if not pictures:
            print("No picture elements found in the DocTags file.")
            return

        print(f"Found {len(pictures)} picture elements.")

        # Load the image from PDF
        page_image = load_pdf_page(args.pdf, args.page, args.dpi)
        print(f"Loaded page {args.page} image: {page_image.size[0]}x{page_image.size[1]}")

        # Adjust coordinates if needed
        if args.adjust:
            # Check if coordinates need normalization
            max_x = max([p['x2'] for p in pictures])
            max_y = max([p['y2'] for p in pictures])

            if max_x <= DEFAULT_GRID_SIZE and max_y <= DEFAULT_GRID_SIZE:
                print(f"Detected normalized coordinates (0-{DEFAULT_GRID_SIZE} grid)")
                pictures = normalize_coordinates(pictures, page_image.width, page_image.height)
            else:
                pictures = auto_adjust_coordinates(pictures, page_image.width, page_image.height)

        # Extract and save pictures
        saved_files = extract_and_save_pictures(
            page_image, pictures, output_dir,
            args.max_width, args.margin
        )

        # Create HTML index
        pdf_name = Path(args.pdf).stem
        create_html_index(pictures, saved_files, pdf_name, args.page, output_dir)

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()