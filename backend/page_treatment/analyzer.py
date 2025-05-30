#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "docling-core",
#     "mlx-vlm",
#     "pillow",
#     "requests",
#     "argparse",
#     "pdf2image",
# ]
# ///

import argparse
import os
import tempfile
import re
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image
from pdf2image import convert_from_bytes
from docling_core.types.doc import ImageRefMode
from docling_core.types.doc.document import DocTagsDocument, DoclingDocument

# Add parent directory to path for imports
import sys
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.utils import ensure_results_folder, load_pdf_page, get_project_root
from backend.config import MODEL_PATH, MAX_TOKENS, DEFAULT_DPI

def parse_arguments():
    """Parse command line arguments."""
    results_dir = ensure_results_folder()

    parser = argparse.ArgumentParser(description='Convert an image or PDF to docling format')
    parser.add_argument('--image', '-i', type=str, required=True,
                        help='Path to local image file, PDF file, or URL')
    parser.add_argument('--prompt', '-p', type=str, default="Convert this page to docling.",
                        help='Prompt for the model')
    parser.add_argument('--output', '-o', type=str, default=str(results_dir / "output.html"),
                        help='Output file path')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number to process for PDF files (starts at 1)')
    parser.add_argument('--dpi', type=int, default=DEFAULT_DPI,
                        help='DPI for PDF rendering')
    parser.add_argument('--start-page', type=int, default=1,
                        help='Start processing PDF from this page number')
    parser.add_argument('--end-page', type=int, default=None,
                        help='Stop processing PDF at this page number')
    return parser.parse_args()

def load_image(image_path, page_num=1, dpi=DEFAULT_DPI):
    """Load image from URL, local image file, or PDF."""
    if urlparse(image_path).scheme in ['http', 'https']:
        response = requests.get(image_path, stream=True, timeout=10)
        response.raise_for_status()

        if image_path.lower().endswith('.pdf') or response.headers.get('Content-Type') == 'application/pdf':
            print(f"Converting PDF from URL (page {page_num})...")
            pdf_images = convert_from_bytes(response.content, dpi=dpi, first_page=page_num, last_page=page_num)
            if not pdf_images:
                raise Exception(f"Could not extract page {page_num} from PDF")
            return pdf_images[0]
        else:
            return Image.open(response.raw)
    else:
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")

        if image_path.suffix.lower() == '.pdf':
            return load_pdf_page(str(image_path), page_num, dpi)
        else:
            return Image.open(image_path)

def process_page(model, processor, config, args, pil_image, page_num=1):
    """Process a single page from a PDF or image file."""
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import stream_generate

    results_dir = ensure_results_folder()

    # For web interface, always use output.doctags.txt
    # For command line with specific pages, use page-specific names
    if args.start_page == args.end_page and args.start_page == page_num:
        # Single page processing
        output_path = results_dir / "output.html"
        doctags_path = results_dir / "output.doctags.txt"
    else:
        # Multi-page processing
        output_path = results_dir / f"output_page{page_num}.html"
        doctags_path = results_dir / f"output_page{page_num}.doctags.txt"

    print(f"Processing page {page_num}")

    # Save image temporarily
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img_file:
        temp_img_path = temp_img_file.name
        pil_image.save(temp_img_path, format='PNG')

    try:
        # Apply chat template and generate
        formatted_prompt = apply_chat_template(processor, config, args.prompt, num_images=1)

        print(f"Generating DocTags for page {page_num}: \n\n")
        output = ""
        for token in stream_generate(
                model, processor, formatted_prompt, [temp_img_path], max_tokens=MAX_TOKENS, verbose=False
        ):
            output += token.text
            print(token.text, end="")
            if "</doctag>" in token.text:
                break
        print("\n\n")

    finally:
        # Clean up temporary file
        if os.path.exists(temp_img_path):
            os.unlink(temp_img_path)

    # Save DocTags output
    with open(doctags_path, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"Raw DocTags saved to: {doctags_path}")

    return output_path

def main():
    args = parse_arguments()

    # Load the model
    print("Loading model...")
    try:
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        model, processor = load(MODEL_PATH)
        config = load_config(MODEL_PATH)
    except Exception as e:
        print(f"Error loading model: {e}")
        return

    # Process the image/PDF
    try:
        # Handle single page or range
        start_page = args.start_page
        end_page = args.end_page or args.page

        for page_num in range(start_page, end_page + 1):
            print(f"\nProcessing page {page_num}...")

            pil_image = load_image(args.image, page_num=page_num, dpi=args.dpi)
            print(f"Page {page_num} loaded: {pil_image.size}")

            process_page(model, processor, config, args, pil_image, page_num)

    except Exception as e:
        print(f"Error processing: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()