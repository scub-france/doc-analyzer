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
#     "pymupdf",  # Optional for better PDF handling
# ]
# ///
import argparse
import os
import tempfile
import re
import base64
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse
import requests
from PIL import Image, UnidentifiedImageError
from pdf2image import convert_from_path, convert_from_bytes
from docling_core.types.doc import ImageRefMode
from docling_core.types.doc.document import DocTagsDocument, DoclingDocument


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

    parser = argparse.ArgumentParser(description='Convert an image or PDF to docling format')
    parser.add_argument('--image', '-i', type=str, required=True,
                        help='Path to local image file, PDF file, or URL')
    parser.add_argument('--prompt', '-p', type=str, default="Convert this page to docling.",
                        help='Prompt for the model')
    parser.add_argument('--output', '-o', type=str, default=str(results_dir / "output.html"),
                        help='Output file path')
    parser.add_argument('--show', '-s', action='store_true',
                        help='Show output in browser')
    parser.add_argument('--page', type=int, default=1,
                        help='Page number to process for PDF files (starts at 1)')
    parser.add_argument('--dpi', type=int, default=200,
                        help='DPI for PDF rendering (higher values produce larger images)')
    parser.add_argument('--debug', '-d', action='store_true',
                        help='Enable debug mode with extra output')
    parser.add_argument('--doctags-only', action='store_true',
                        help='Generate only raw DocTags output without processing')
    parser.add_argument('--all-pages', '-a', action='store_true',
                        help='Process all pages in a PDF without asking')
    parser.add_argument('--start-page', type=int, default=1,
                        help='Start processing PDF from this page number')
    parser.add_argument('--end-page', type=int, default=None,
                        help='Stop processing PDF at this page number')
    parser.add_argument('--max-pages', type=int, default=None,
                        help='Maximum number of pages to process')
    return parser.parse_args()


def load_image(image_path, page_num=1, dpi=200):
    """Load image from URL, local image file, or PDF."""
    if urlparse(image_path).scheme in ['http', 'https']:  # it is a URL
        try:
            response = requests.get(image_path, stream=True, timeout=10)
            response.raise_for_status()
            content = response.content

            # Check if it's a PDF
            if image_path.lower().endswith('.pdf') or response.headers.get('Content-Type') == 'application/pdf':
                print(f"Converting PDF from URL (page {page_num})...")
                pdf_images = convert_from_bytes(content, dpi=dpi, first_page=page_num, last_page=page_num)
                if not pdf_images:
                    raise Exception(f"Could not extract page {page_num} from PDF")
                return pdf_images[0]  # Return the first (and only) page
            else:
                return Image.open(BytesIO(content))
        except requests.exceptions.RequestException as e:
            raise Exception(f"Error loading image from URL: {e}")
    else:  # it is a local file
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"File not found: {image_path}")

        # Check if it's a PDF
        if image_path.suffix.lower() == '.pdf':
            print(f"Converting PDF to image (page {page_num}, DPI: {dpi})...")
            try:
                pdf_images = convert_from_path(
                    image_path,
                    dpi=dpi,
                    first_page=page_num,
                    last_page=page_num
                )
                if not pdf_images:
                    raise Exception(f"Could not extract page {page_num} from PDF")
                return pdf_images[0]  # Return the requested page
            except Exception as e:
                raise Exception(f"Error converting PDF to image: {e}")
        else:
            try:
                return Image.open(image_path)
            except UnidentifiedImageError:
                raise Exception(f"Cannot identify image file: {image_path}. Make sure it's a valid image format or PDF.")


def cleanup_doctags(doctags_text):
    """Clean up the DocTags structure."""
    print("Cleaning up DocTags structure...")

    # Simplified approach to extract valuable information
    # Extract headers
    headers = re.findall(r'<section_header_level_1>.*?>(.*?)</section_header_level_1>', doctags_text)

    # Extract text paragraphs
    paragraphs = re.findall(r'<text>.*?>(.*?)</text>', doctags_text)

    # Extract list items
    list_items = re.findall(r'<list_item>.*?>(.*?)</list_item>', doctags_text)

    # Extract footer
    footer = re.search(r'<page_footer>.*?>(.*?)</page_footer>', doctags_text)
    footer_text = footer.group(1) if footer else ""

    # Create a clean doctags structure
    clean_doctags = "<doctag>\n"

    # Add headers
    for header in headers:
        clean_doctags += f"<section_header_level_1>{header}</section_header_level_1>\n"

    # Add text
    for paragraph in paragraphs:
        clean_doctags += f"<text>{paragraph}</text>\n"

    # Add list if any items found
    if list_items:
        clean_doctags += "<unordered_list>\n"
        for item in list_items:
            clean_doctags += f"<list_item>{item}</list_item>\n"
        clean_doctags += "</unordered_list>\n"

    # Add footer if present
    if footer_text:
        clean_doctags += f"<page_footer>{footer_text}</page_footer>\n"

    clean_doctags += "</doctag>"

    return clean_doctags


def extract_all_tags(doctags_text):
    """Extract all unique DocTags from the text."""
    print("Extracting all DocTags...")

    # Use regex to find all tags
    tag_pattern = r'</?(\w+)(?:\s[^>]*)?>'
    all_tags = re.findall(tag_pattern, doctags_text)

    # Remove duplicates and sort
    unique_tags = sorted(set(all_tags))

    # Create a list of tags with their frequencies
    tag_counts = {}
    for tag in all_tags:
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    # Format the output
    tags_output = "# DocTags Found\n\n"
    tags_output += "| Tag | Count |\n"
    tags_output += "|-----|-------|\n"

    for tag in unique_tags:
        tags_output += f"| {tag} | {tag_counts[tag]} |\n"

    # Add examples section
    tags_output += "\n\n# DocTags Examples\n\n"

    # Find example usages for each tag
    for tag in unique_tags:
        # Find an opening tag with content
        open_pattern = f'<{tag}(?:\\s[^>]*)?>.*?</{tag}>'
        examples = re.findall(open_pattern, doctags_text, re.DOTALL)

        if examples:
            # Limit to first example
            example = examples[0]
            # Truncate if too long
            if len(example) > 200:
                example = example[:197] + "..."

            tags_output += f"## {tag}\n\n```xml\n{example}\n```\n\n"

    return tags_output


def debug_doctags(doctags_text, debug_mode=False):
    """Debug function to analyze doctag structure."""
    if not debug_mode:
        return doctags_text

    print("\nAnalyzing DocTags structure:")
    print(f"Total length: {len(doctags_text)} characters")

    # Check for valid opening and closing tags
    opening_tags = []
    i = 0
    while i < len(doctags_text):
        open_tag_start = doctags_text.find('<', i)
        if open_tag_start == -1:
            break

        open_tag_end = doctags_text.find('>', open_tag_start)
        if open_tag_end == -1:
            print(f"WARNING: Unclosed tag starting at position {open_tag_start}")
            break

        tag_content = doctags_text[open_tag_start+1:open_tag_end]
        if tag_content.startswith('/'):
            # This is a closing tag
            if not opening_tags:
                print(f"WARNING: Closing tag {tag_content} without matching opening tag")
            else:
                last_open = opening_tags.pop()
                if last_open != tag_content[1:]:
                    print(f"WARNING: Mismatched tags: opening <{last_open}> vs closing <{tag_content}>")
        elif not tag_content.startswith('!') and not ' ' in tag_content:
            # This is an opening tag (not a comment or self-closing)
            opening_tags.append(tag_content)

        i = open_tag_end + 1

    if opening_tags:
        print(f"WARNING: Unclosed tags: {', '.join(opening_tags)}")

    # Count all tags
    tag_counts = {}
    tag_pattern = r'<(\w+)(?:\s|>)'
    import re
    for tag in re.findall(tag_pattern, doctags_text):
        tag_counts[tag] = tag_counts.get(tag, 0) + 1

    print("Tag counts:")
    for tag, count in tag_counts.items():
        print(f"  <{tag}>: {count}")

    # Special check for doctag
    if doctags_text.count('<doctag>') != 1:
        print(f"WARNING: Expected 1 <doctag> tag, found {doctags_text.count('<doctag>')}")
    if doctags_text.count('</doctag>') != 1:
        print(f"WARNING: Expected 1 </doctag> tag, found {doctags_text.count('</doctag>')}")

    return doctags_text


def create_html_document(image_path, doctags_text, pil_image, args):
    """Create HTML directly from DocTags and image."""
    print("Creating HTML document directly...")

    # Get filename for document title
    doc_name = Path(image_path).stem

    # Extract content from doctags
    title_match = re.search(r'<section_header_level_1>.*?>(.*?)</section_header_level_1>', doctags_text)
    title = title_match.group(1) if title_match else doc_name

    # Clean title by removing any location tags
    title = re.sub(r'<loc_\d+>', '', title)

    # Extract text content
    text_matches = re.findall(r'<text>.*?>(.*?)</text>', doctags_text)
    paragraphs = []
    for text in text_matches:
        # Clean text by removing any location tags
        cleaned_text = re.sub(r'<loc_\d+>', '', text)
        paragraphs.append(cleaned_text)

    # Extract list items
    list_items = []
    item_matches = re.findall(r'<list_item>.*?>(.*?)</list_item>', doctags_text)
    for item in item_matches:
        # Clean item by removing any location tags
        cleaned_item = re.sub(r'<loc_\d+>', '', item)
        list_items.append(cleaned_item)

    # Extract footer
    footer_match = re.search(r'<page_footer>.*?>(.*?)</page_footer>', doctags_text)
    footer_text = ""
    if footer_match:
        footer_text = re.sub(r'<loc_\d+>', '', footer_match.group(1))

    # Create image data URI
    max_dimension = 1200
    img_for_embedding = pil_image
    if max(pil_image.size) > max_dimension:
        ratio = min(max_dimension / pil_image.size[0], max_dimension / pil_image.size[1])
        new_size = (int(pil_image.size[0] * ratio), int(pil_image.size[1] * ratio))
        img_for_embedding = pil_image.resize(new_size, Image.LANCZOS)

    buffered = BytesIO()
    img_for_embedding.save(buffered, format="PNG", optimize=True, quality=90)
    img_str = base64.b64encode(buffered.getvalue()).decode()
    img_data_uri = f"data:image/png;base64,{img_str}"

    # Build HTML paragraphs
    paragraphs_html = "".join([f"<p>{text}</p>\n" for text in paragraphs]) if paragraphs else ""

    # Build list HTML
    list_html = ""
    if list_items:
        list_html = "<ul>\n"
        for item in list_items:
            list_html += f"<li>{item}</li>\n"
        list_html += "</ul>\n"

    # Create footer HTML
    footer_html = f"<div class='page-footer'>{footer_text}</div>\n" if footer_text else ""

    # Create HTML document
    html_content = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
    body {{ font-family: Arial, sans-serif; margin: 0 auto; max-width: 800px; padding: 20px; line-height: 1.6; }}
    img {{ max-width: 100%; height: auto; }}
    h1 {{ color: #333; border-bottom: 1px solid #eee; padding-bottom: 10px; }}
    figure {{ margin: 20px 0; text-align: center; }}
    figcaption {{ color: #666; font-style: italic; margin-top: 5px; }}
    ul {{ margin-left: 20px; padding-left: 20px; }}
    li {{ margin-bottom: 10px; }}
    .page-footer {{ color: #666; margin-top: 20px; border-top: 1px solid #eee; padding-top: 5px; text-align: center; }}
</style>
</head>
<body>
<div class='page'>
<h1>{title}</h1>
<figure>
  <img src="{img_data_uri}" alt="Document Image"/>
  <figcaption>Page {args.page}</figcaption>
</figure>
{paragraphs_html}
{list_html}
{footer_html}
</div>
</body>
</html>'''

    return html_content


def create_markdown_document(image_path, doctags_text, args):
    """Create Markdown document from DocTags."""
    print("Creating Markdown document...")

    # Get filename for document title
    doc_name = Path(image_path).stem

    # Extract content from doctags
    title_match = re.search(r'<section_header_level_1>.*?>(.*?)</section_header_level_1>', doctags_text)
    title = title_match.group(1) if title_match else doc_name

    # Clean title by removing any location tags
    title = re.sub(r'<loc_\d+>', '', title)

    # Extract text content
    text_matches = re.findall(r'<text>.*?>(.*?)</text>', doctags_text)
    paragraphs = []
    for text in text_matches:
        # Clean text by removing any location tags
        cleaned_text = re.sub(r'<loc_\d+>', '', text)
        paragraphs.append(cleaned_text)

    # Extract list items
    list_items = []
    item_matches = re.findall(r'<list_item>.*?>(.*?)</list_item>', doctags_text)
    for item in item_matches:
        # Clean item by removing any location tags
        cleaned_item = re.sub(r'<loc_\d+>', '', item)
        list_items.append(cleaned_item)

    # Extract footer
    footer_match = re.search(r'<page_footer>.*?>(.*?)</page_footer>', doctags_text)
    footer_text = ""
    if footer_match:
        footer_text = re.sub(r'<loc_\d+>', '', footer_match.group(1))

    # Build markdown content
    markdown = f"# {title}\n\n"
    markdown += f"*Page {args.page}*\n\n"

    # Add paragraphs
    for p in paragraphs:
        markdown += f"{p}\n\n"

    # Add list
    if list_items:
        for item in list_items:
            markdown += f"* {item}\n"
        markdown += "\n"

    # Add footer
    if footer_text:
        markdown += f"---\n{footer_text}\n"

    return markdown


def process_page(args, model, processor, config, image_path, pil_image, page_num=1):
    """Process a single page from a PDF or image file."""
    from mlx_vlm.prompt_utils import apply_chat_template
    from mlx_vlm.utils import stream_generate

    # Ensure results folder exists
    results_dir = ensure_results_folder()

    # Prepare input
    prompt = args.prompt
    output_base = Path(args.output)
    output_path = output_base

    # If processing PDF and output is a path without explicit numbering, add page numbers
    if Path(image_path).suffix.lower() == '.pdf' and page_num > 1:
        # Get base filename without extension
        base_name = output_base.stem
        output_path = results_dir / f"{base_name}_page{page_num}{output_base.suffix}"

    print(f"Processing page {page_num}, output will be saved to {output_path}")

    # Create a temporary file for the image
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as temp_img_file:
        temp_img_path = temp_img_file.name
        pil_image.save(temp_img_path, format='PNG')
        print(f"Saved temporary image to: {temp_img_path}")

    try:
        # Apply chat template
        formatted_prompt = apply_chat_template(processor, config, prompt, num_images=1)

        # Generate output
        print(f"Generating DocTags for page {page_num}: \n\n")
        output = ""
        for token in stream_generate(
                model, processor, formatted_prompt, [temp_img_path], max_tokens=4096, verbose=False
        ):
            output += token.text
            print(token.text, end="")
            if "</doctag>" in token.text:
                break
        print("\n\n")

        # Debug and clean the doctags content
        output = debug_doctags(output, args.debug)

        # Extract all tags if in DocTags-only mode
        if args.doctags_only:
            tags_analysis = extract_all_tags(output)

        # Clean the output for document creation
        cleaned_output = cleanup_doctags(output)
    finally:
        # Clean up the temporary file
        if os.path.exists(temp_img_path):
            os.unlink(temp_img_path)
            print(f"Removed temporary image file")

    # Save the raw DocTags to a txt file in results folder
    doctags_path = results_dir / f"{output_path.stem}.doctags.txt"
    with open(doctags_path, 'w', encoding='utf-8') as f:
        f.write(output)
    print(f"Raw DocTags saved to: {doctags_path}")

    # Save the tag analysis if in DocTags-only mode
    if args.doctags_only:
        tags_path = results_dir / f"{output_path.stem}.tags.md"
        with open(tags_path, 'w', encoding='utf-8') as f:
            f.write(tags_analysis)
        print(f"DocTags analysis saved to: {tags_path}")

    # If not in DocTags-only mode, create documents
    if not args.doctags_only:
        # Create markdown document
        md_content = create_markdown_document(image_path, output, args)
        md_path = results_dir / f"{output_path.stem}.md"
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(md_content)
        print(f"Markdown saved to: {md_path}")

        # Create HTML document
        html_content = create_html_document(image_path, output, pil_image, args)
        html_path = results_dir / f"{output_path.stem}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"HTML saved to: {html_path}")

        # Calculate final file size
        html_size = os.path.getsize(html_path)
        print(f"Final HTML file size: {html_size} bytes")

        # Open in browser if requested (only for the first page or single pages)
        if args.show and html_size > 100 and page_num <= 1:
            import webbrowser
            webbrowser.open(f"file:///{str(html_path.resolve())}")

    # Save a copy of the processed image for reference if in debug mode
    if args.debug:
        img_debug_path = results_dir / f"{output_path.stem}.debug.png"
        pil_image.save(img_debug_path)
        print(f"Saved debug image to: {img_debug_path}")

    return output_path


def main():
    # Ensure results folder exists
    ensure_results_folder()

    # Parse arguments
    args = parse_arguments()

    # Settings
    DEBUG_MODE = args.debug
    DOCTAGS_ONLY = args.doctags_only
    image_path = args.image

    # Load the model
    print("Loading model...")
    try:
        from mlx_vlm import load, generate
        from mlx_vlm.utils import load_config

        model_path = "ds4sd/SmolDocling-256M-preview-mlx-bf16"
        model, processor = load(model_path)
        config = load_config(model_path)
    except Exception as e:
        print(f"Error loading model: {e}")
        import traceback
        traceback.print_exc()
        return

    # Check if the input is a PDF
    pdf_path = Path(image_path)
    is_pdf = False
    pdf_page_count = 0

    if pdf_path.suffix.lower() == '.pdf':
        is_pdf = True
        # Try to get page count
        try:
            try:
                import fitz  # PyMuPDF
                pdf_document = fitz.open(pdf_path)
                pdf_page_count = len(pdf_document)
                print(f"PDF detected with {pdf_page_count} pages")
                pdf_document.close()
            except ImportError:
                print("PyMuPDF not installed. Using pdf2image to estimate page count...")
                from pdf2image import pdfinfo_from_path
                pdf_info = pdfinfo_from_path(pdf_path)
                pdf_page_count = pdf_info["Pages"]
                print(f"PDF detected with {pdf_page_count} pages")
        except Exception as e:
            print(f"Could not determine PDF page count: {e}")
            print("Will process the specified page only.")
            pdf_page_count = args.page

    # Determine which pages to process
    process_all_pages = args.all_pages
    start_page = args.start_page
    end_page = args.end_page if args.end_page else pdf_page_count
    max_pages = args.max_pages

    # Validate page ranges
    if start_page < 1:
        start_page = 1
    if end_page and end_page > pdf_page_count:
        end_page = pdf_page_count

    # Ask user if they want to process all pages or just one (if not specified by arguments)
    if is_pdf and pdf_page_count > 1 and not process_all_pages and args.start_page == 1 and not args.end_page:
        if args.page > 1:
            print(f"You specified to process page {args.page}.")
            process_all_pages = False
            start_page = args.page
            end_page = args.page
        else:
            user_input = input("Do you want to process all pages? [y/N]: ")
            process_all_pages = user_input.lower() in ['y', 'yes']
            if not process_all_pages:
                # Ask for specific page or range
                page_input = input(f"Enter page number(s) to process (e.g., 3 or 1-5) [1]: ")
                if page_input.strip():
                    if '-' in page_input:
                        try:
                            start_str, end_str = page_input.split('-')
                            start_page = int(start_str.strip())
                            end_page = int(end_str.strip())
                        except ValueError:
                            print("Invalid range format. Using default page 1.")
                            start_page = end_page = 1
                    else:
                        try:
                            start_page = end_page = int(page_input.strip())
                        except ValueError:
                            print("Invalid page number. Using default page 1.")
                            start_page = end_page = 1

    # Apply max_pages limit if specified
    if max_pages and end_page - start_page + 1 > max_pages:
        end_page = start_page + max_pages - 1

    # Process pages
    if is_pdf and (process_all_pages or start_page != end_page):
        page_range = range(start_page, end_page + 1)
        print(f"Processing pages {start_page} to {end_page} ({len(page_range)} pages)...")
        processed_pages = []

        for page_num in page_range:
            print(f"\n{'='*50}\nProcessing PDF page {page_num}/{end_page}\n{'='*50}\n")

            # Update the page argument
            args.page = page_num

            # Load the specific page
            try:
                pil_image = load_image(image_path, page_num=page_num, dpi=args.dpi)
                print(f"Page {page_num} loaded: {pil_image.size}")

                # Process the page
                output_path = process_page(args, model, processor, config, image_path, pil_image, page_num)
                processed_pages.append(output_path)
            except Exception as e:
                print(f"Error processing page {page_num}: {e}")
                import traceback
                traceback.print_exc()
                continue

        print(f"\nProcessed {len(processed_pages)} pages from PDF.")
        print(f"Output files: {', '.join([str(p) for p in processed_pages])}")
    else:
        # Process just one page (either it's not a PDF or user only wants one page)
        try:
            # Load image resource
            print(f"Loading {'PDF page' if is_pdf else 'image'} from: {image_path}")
            pil_image = load_image(image_path, page_num=args.page, dpi=args.dpi)
            print(f"Image loaded: {pil_image.size}")

            # Process the single page
            process_page(args, model, processor, config, image_path, pil_image)
        except Exception as e:
            print(f"Error processing {image_path}: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()