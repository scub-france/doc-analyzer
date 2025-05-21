#!/usr/bin/env python3
"""
DocTags Picture Extractor - Extract <picture> elements from DocTags and save as separate image files.

Usage:
    python picture_extractor.py --doctags output.doctags.txt --pdf document.pdf --page 1 --output pictures
"""

import argparse
import os
import re
import sys
from io import BytesIO
from pathlib import Path
import pdf2image
from PIL import Image

# Regular expression to extract picture location data
PICTURE_PATTERN = r'<picture>.*?<loc_(\d+)><loc_(\d+)><loc_(\d+)><loc_(\d+)>(.*?)</picture>'

def ensure_results_folder(custom_path=None):
    """Create the results folder if it doesn't exist."""
    if custom_path:
        results_dir = Path(custom_path)
    else:
        results_dir = Path("results")

    if not results_dir.exists():
        results_dir.mkdir(parents=True)
        print(f"Created directory: {results_dir}")
    return results_dir

def parse_arguments():
    """Parse command line arguments."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Extract pictures from DocTags format')
    parser.add_argument('--doctags', '-d', type=str, required=True,
                        help='Path to DocTags file')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to original PDF file')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number in PDF (starts at 1, default: 1)')
    parser.add_argument('--output', '-o', type=str, default=str(results_dir / "pictures"),
                        help='Output directory for extracted pictures')
    parser.add_argument('--dpi', type=int, default=300,
                        help='DPI for PDF rendering (higher values produce larger images)')
    parser.add_argument('--max-width', type=int, default=1200,
                        help='Maximum width of output images in pixels')
    parser.add_argument('--adjust', action='store_true',
                        help='Try to automatically adjust scaling')
    parser.add_argument('--scale', type=float, default=1.0,
                        help='Scaling factor for coordinates (default: 1.0)')
    parser.add_argument('--scale-x', type=float, default=None,
                        help='X-axis scaling factor (overrides --scale)')
    parser.add_argument('--scale-y', type=float, default=None,
                        help='Y-axis scaling factor (overrides --scale)')
    parser.add_argument('--margin', type=int, default=0,
                        help='Add margin around extracted pictures in pixels')
    parser.add_argument('--show', '-s', action='store_true',
                        help='Open a file browser to the output directory when done')
    return parser.parse_args()

def load_image_from_pdf(pdf_path, page_num=1, dpi=300):
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

def extract_pictures_from_doctags(doctags_path):
    """Parse DocTags file and extract picture elements with their coordinates."""
    if not os.path.exists(doctags_path):
        raise FileNotFoundError(f"DocTags file not found: {doctags_path}")

    with open(doctags_path, 'r', encoding='utf-8') as f:
        doctags_content = f.read()

    # Find all picture elements with location information
    pictures = []
    picture_matches = re.finditer(PICTURE_PATTERN, doctags_content, re.DOTALL)

    for i, match in enumerate(picture_matches):
        x1, y1, x2, y2, caption = match.groups()

        # Extract caption if available (remove location tags)
        clean_caption = re.sub(r'<loc_\d+>', '', caption).strip()

        pictures.append({
            'id': i + 1,
            'x1': int(x1),
            'y1': int(y1),
            'x2': int(x2),
            'y2': int(y2),
            'caption': clean_caption
        })

    return pictures

def normalize_coordinates(pictures, image_width, image_height, grid_size=500):
    """
    Normalize coordinates from the DocTags grid (0-500) to actual image dimensions.
    """
    normalized_pictures = []

    for picture in pictures:
        # Clone the picture
        new_picture = picture.copy()

        # Convert from grid coordinates to actual page dimensions
        new_picture['x1'] = int(picture['x1'] * image_width / grid_size)
        new_picture['y1'] = int(picture['y1'] * image_height / grid_size)
        new_picture['x2'] = int(picture['x2'] * image_width / grid_size)
        new_picture['y2'] = int(picture['y2'] * image_height / grid_size)

        normalized_pictures.append(new_picture)

    return normalized_pictures

def auto_adjust_coordinates(pictures, image_width, image_height):
    """
    Automatically adjust coordinates based on image dimensions.
    """
    if not pictures:
        return pictures

    # Find the maximum coordinates
    max_x = max([pic['x2'] for pic in pictures])
    max_y = max([pic['y2'] for pic in pictures])

    # If coordinates seem to be in a normalized grid (0-500 range)
    if max_x <= 500 and max_y <= 500:
        print(f"Detected normalized coordinates (0-500 grid)")
        return normalize_coordinates(pictures, image_width, image_height)

    # Calculate appropriate scaling factors with better heuristics
    if max_x > 0:
        x_scale = min(image_width / max_x, 1.0) if max_x > image_width else max(image_width / max_x, 0.5)
        print(f"Auto-adjusted X scale to {x_scale:.3f} (image width: {image_width}, max picture x: {max_x})")
    else:
        x_scale = 1.0

    if max_y > 0:
        y_scale = min(image_height / max_y, 1.0) if max_y > image_height else max(image_height / max_y, 0.5)
        print(f"Auto-adjusted Y scale to {y_scale:.3f} (image height: {image_height}, max picture y: {max_y})")
    else:
        y_scale = 1.0

    # Apply more aggressive adjustment if image and pictures are very different in scale
    if max_x > image_width * 5 or max_x < image_width / 5:
        x_scale = image_width / max_x
        print(f"Major X scale adjustment to {x_scale:.3f}")

    if max_y > image_height * 5 or max_y < image_height / 5:
        y_scale = image_height / max_y
        print(f"Major Y scale adjustment to {y_scale:.3f}")

    # Apply the scaling to all pictures
    adjusted_pictures = []
    for pic in pictures:
        adjusted_pic = pic.copy()
        adjusted_pic['x1'] = int(pic['x1'] * x_scale)
        adjusted_pic['y1'] = int(pic['y1'] * y_scale)
        adjusted_pic['x2'] = int(pic['x2'] * x_scale)
        adjusted_pic['y2'] = int(pic['y2'] * y_scale)
        adjusted_pictures.append(adjusted_pic)

    print(f"Applied auto-scaling: X={x_scale}, Y={y_scale}")
    return adjusted_pictures

def extract_and_save_pictures(image, pictures, output_dir, max_width=1200, margin=0):
    """Extract picture regions from the image and save them as separate files."""
    # Ensure output directory exists
    output_path = ensure_results_folder(output_dir)
    saved_files = []

    # Process each picture
    for picture in pictures:
        try:
            # Add margin to coordinates if specified
            x1 = max(0, picture['x1'] - margin)
            y1 = max(0, picture['y1'] - margin)
            x2 = min(image.width, picture['x2'] + margin)
            y2 = min(image.height, picture['y2'] + margin)

            # Check if coordinates are valid
            if x1 >= x2 or y1 >= y2 or x1 < 0 or y1 < 0 or x2 > image.width or y2 > image.height:
                print(f"Warning: Invalid coordinates for picture {picture['id']}: ({x1},{y1})-({x2},{y2})")
                continue

            # Crop the image
            cropped_img = image.crop((x1, y1, x2, y2))

            # Resize if necessary
            if cropped_img.width > max_width:
                ratio = max_width / cropped_img.width
                new_height = int(cropped_img.height * ratio)
                cropped_img = cropped_img.resize((max_width, new_height), Image.LANCZOS)

            # Generate filename
            caption = picture['caption']
            if caption:
                # Create a filename-safe version of the caption (first 30 chars)
                safe_caption = re.sub(r'[^\w\s-]', '', caption)[:30].strip().replace(' ', '_').lower()
                filename = f"picture_{picture['id']}_{safe_caption}.png"
            else:
                filename = f"picture_{picture['id']}.png"

            # Save the image
            output_file = output_path / filename
            cropped_img.save(output_file, format="PNG")

            # Create a text file with the caption if available
            if caption:
                caption_file = output_path / f"{output_file.stem}.txt"
                with open(caption_file, 'w', encoding='utf-8') as f:
                    f.write(caption)

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
        .picture-caption {{ 
            margin-top: 10px;
            color: #555;
        }}
        .picture-coords {{ 
            margin-top: 5px;
            font-size: 0.8em;
            color: #777;
        }}
        .no-pictures {{ 
            background-color: white;
            padding: 20px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
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
        html += """    <div class="gallery">
"""

        for picture, file_path in zip(pictures, saved_files):
            # Get relative path for the image
            rel_path = file_path.name

            html += f"""        <div class="picture-card">
            <img src="{rel_path}" alt="Picture {picture['id']}">
            <div class="picture-info">
                <h3>Picture {picture['id']}</h3>
"""

            if picture['caption']:
                html += f"""                <div class="picture-caption">{picture['caption']}</div>
"""

            html += f"""                <div class="picture-coords">Coordinates: ({picture['x1']},{picture['y1']})-({picture['x2']},{picture['y2']})</div>
            </div>
        </div>
"""

        html += """    </div>
"""
    else:
        html += """    <div class="no-pictures">
        <h2>No pictures found on this page</h2>
        <p>The DocTags file doesn't contain any picture elements for this page.</p>
    </div>
"""

    html += """</body>
</html>
"""

    # Save the HTML file
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"Created index file: {index_file}")
    return index_file

def main():
    # Parse arguments
    args = parse_arguments()

    # Create output directory
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
        page_image = load_image_from_pdf(args.pdf, args.page, args.dpi)
        print(f"Loaded page {args.page} image: {page_image.size[0]}x{page_image.size[1]}")

        # Process coordinates
        if args.adjust:
            pictures = auto_adjust_coordinates(pictures, page_image.width, page_image.height)
        elif args.scale != 1.0 or args.scale_x is not None or args.scale_y is not None:
            # Apply manual scaling
            scale_x = args.scale_x if args.scale_x is not None else args.scale
            scale_y = args.scale_y if args.scale_y is not None else args.scale

            print(f"Applying manual scaling: X={scale_x}, Y={scale_y}")
            for picture in pictures:
                picture['x1'] = int(picture['x1'] * scale_x)
                picture['y1'] = int(picture['y1'] * scale_y)
                picture['x2'] = int(picture['x2'] * scale_x)
                picture['y2'] = int(picture['y2'] * scale_y)

        # Extract and save pictures
        saved_files = extract_and_save_pictures(
            page_image,
            pictures,
            output_dir,
            args.max_width,
            args.margin
        )

        # Create HTML index
        pdf_name = Path(args.pdf).stem
        index_file = create_html_index(pictures, saved_files, pdf_name, args.page, output_dir)

        # Open the output directory or index file if requested
        if args.show and saved_files:
            import webbrowser
            if sys.platform == 'darwin':  # macOS
                import subprocess
                subprocess.run(['open', str(output_dir)])
            elif sys.platform == 'win32':  # Windows
                import os
                os.startfile(str(output_dir))
            else:  # Linux
                webbrowser.open(f"file:///{os.path.abspath(index_file)}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()