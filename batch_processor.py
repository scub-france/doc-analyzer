#!/usr/bin/env python3
"""
DocTags Batch Processor - Process multiple pages from a PDF in sequence.

Usage:
    python batch_processor.py --pdf document.pdf --start 1 --end 10 --adjust
"""

import argparse
import subprocess
import os
import sys
import time
import json
from pathlib import Path
from datetime import datetime

def ensure_results_folder():
    """Create the results folder if it doesn't exist."""
    results_dir = Path("results")
    if not results_dir.exists():
        results_dir.mkdir()
        print(f"Created results directory: {results_dir}")
    return results_dir

def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Batch process multiple PDF pages')
    parser.add_argument('--pdf', '-p', type=str, required=True,
                        help='Path to PDF file')
    parser.add_argument('--start', type=int, default=1,
                        help='Starting page number (default: 1)')
    parser.add_argument('--end', type=int, default=None,
                        help='Ending page number (default: last page)')
    parser.add_argument('--pages', type=str, default=None,
                        help='Comma-separated list of specific pages (e.g., "1,3,5-7,10")')
    parser.add_argument('--adjust', action='store_true',
                        help='Auto-adjust coordinates for visualizer and extractor')
    parser.add_argument('--skip-analyzer', action='store_true',
                        help='Skip analyzer step (use existing doctags)')
    parser.add_argument('--skip-visualizer', action='store_true',
                        help='Skip visualizer step')
    parser.add_argument('--skip-extractor', action='store_true',
                        help='Skip extractor step')
    parser.add_argument('--output-dir', type=str, default='results',
                        help='Output directory for all results')
    parser.add_argument('--dpi', type=int, default=200,
                        help='DPI for PDF rendering')
    parser.add_argument('--max-pages', type=int, default=None,
                        help='Maximum number of pages to process')
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Verbose output')
    return parser.parse_args()

def get_pdf_page_count(pdf_path):
    """Get the number of pages in a PDF file."""
    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(pdf_path)
        return info["Pages"]
    except Exception as e:
        print(f"Warning: Could not determine page count: {e}")
        return None

def parse_page_list(pages_str):
    """Parse a page list string like "1,3,5-7,10" into a list of page numbers."""
    pages = []
    parts = pages_str.split(',')

    for part in parts:
        part = part.strip()
        if '-' in part:
            # Range like "5-7"
            try:
                start, end = map(int, part.split('-'))
                pages.extend(range(start, end + 1))
            except ValueError:
                print(f"Warning: Invalid page range '{part}'")
        else:
            # Single page
            try:
                pages.append(int(part))
            except ValueError:
                print(f"Warning: Invalid page number '{part}'")

    # Remove duplicates and sort
    return sorted(set(pages))

def run_command(command, verbose=False):
    """Run a command and return success status and output."""
    if verbose:
        print(f"Running: {command}")

    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        # Send "n" to bypass any prompts
        stdout, stderr = process.communicate(input="n\n", timeout=300)  # 5 minute timeout

        if verbose and stdout:
            print("Output:", stdout[:500], "..." if len(stdout) > 500 else "")

        if process.returncode != 0:
            print(f"Error: {stderr}")
            return False, stdout, stderr

        return True, stdout, stderr

    except subprocess.TimeoutExpired:
        print("Error: Command timed out")
        return False, "", "Command timed out"
    except Exception as e:
        print(f"Error running command: {e}")
        return False, "", str(e)

def process_page(pdf_path, page_num, args, results_dir):
    """Process a single page through all three steps."""
    print(f"\n{'='*60}")
    print(f"Processing page {page_num}")
    print(f"{'='*60}")

    page_results = {
        'page': page_num,
        'analyzer': {'success': False},
        'visualizer': {'success': False},
        'extractor': {'success': False},
        'start_time': datetime.now().isoformat()
    }

    # Step 1: Analyzer
    if not args.skip_analyzer:
        print(f"\n[1/3] Running analyzer for page {page_num}...")

        # Create page-specific output name
        output_name = f"page_{page_num}"
        analyzer_cmd = f"python analyzer.py --image {pdf_path} --page {page_num} --output {results_dir}/{output_name}.html --dpi {args.dpi}"

        success, stdout, stderr = run_command(analyzer_cmd, args.verbose)

        page_results['analyzer'] = {
            'success': success,
            'doctags_file': f"{results_dir}/{output_name}.doctags.txt" if success else None,
            'error': stderr if not success else None
        }

        if success:
            print(f"✓ Analyzer completed for page {page_num}")
        else:
            print(f"✗ Analyzer failed for page {page_num}")
            if not args.skip_visualizer or not args.skip_extractor:
                print(f"Skipping remaining steps for page {page_num} due to analyzer failure")
                return page_results
    else:
        # Check if doctags file exists
        doctags_file = f"{results_dir}/page_{page_num}.doctags.txt"
        if os.path.exists(doctags_file):
            page_results['analyzer'] = {
                'success': True,
                'doctags_file': doctags_file,
                'skipped': True
            }
        else:
            print(f"✗ No existing doctags file found for page {page_num}")
            return page_results

    # Step 2: Visualizer
    if not args.skip_visualizer:
        print(f"\n[2/3] Running visualizer for page {page_num}...")

        doctags_file = page_results['analyzer']['doctags_file']
        visualizer_cmd = f"python visualizer.py --doctags {doctags_file} --pdf {pdf_path} --page {page_num}"

        if args.adjust:
            visualizer_cmd += " --adjust"

        success, stdout, stderr = run_command(visualizer_cmd, args.verbose)

        page_results['visualizer'] = {
            'success': success,
            'image_file': f"{results_dir}/visualization_page_{page_num}.png" if success else None,
            'error': stderr if not success else None
        }

        if success:
            print(f"✓ Visualizer completed for page {page_num}")
        else:
            print(f"✗ Visualizer failed for page {page_num}")

    # Step 3: Picture Extractor
    if not args.skip_extractor:
        print(f"\n[3/3] Running picture extractor for page {page_num}...")

        doctags_file = page_results['analyzer']['doctags_file']
        pictures_dir = f"{results_dir}/pictures_page_{page_num}"
        extractor_cmd = f"python picture_extractor.py --doctags {doctags_file} --pdf {pdf_path} --page {page_num} --output {pictures_dir}"

        if args.adjust:
            extractor_cmd += " --adjust"

        success, stdout, stderr = run_command(extractor_cmd, args.verbose)

        page_results['extractor'] = {
            'success': success,
            'output_dir': pictures_dir if success else None,
            'error': stderr if not success else None
        }

        if success:
            print(f"✓ Picture extractor completed for page {page_num}")
        else:
            print(f"✗ Picture extractor failed for page {page_num}")

    page_results['end_time'] = datetime.now().isoformat()
    return page_results

def create_batch_report(results, pdf_path, output_dir):
    """Create an HTML report summarizing the batch processing results."""
    report_path = Path(output_dir) / "batch_report.html"

    total_pages = len(results)
    successful_pages = sum(1 for r in results if all(
        r.get(step, {}).get('success', False) or r.get(step, {}).get('skipped', False)
        for step in ['analyzer', 'visualizer', 'extractor']
    ))

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Batch Processing Report - {os.path.basename(pdf_path)}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #333; border-bottom: 2px solid #4CAF50; padding-bottom: 10px; }}
        .summary {{ background-color: #f0f0f0; padding: 15px; border-radius: 5px; margin: 20px 0; }}
        .summary-stat {{ display: inline-block; margin-right: 30px; }}
        .summary-stat strong {{ color: #4CAF50; font-size: 24px; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 20px; }}
        th, td {{ padding: 10px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #4CAF50; color: white; }}
        tr:hover {{ background-color: #f5f5f5; }}
        .success {{ color: #4CAF50; font-weight: bold; }}
        .failed {{ color: #f44336; font-weight: bold; }}
        .skipped {{ color: #777; font-style: italic; }}
        .page-link {{ text-decoration: none; color: #2196F3; }}
        .page-link:hover {{ text-decoration: underline; }}
        .timestamp {{ color: #777; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Batch Processing Report</h1>
        <p class="timestamp">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="summary">
            <h2>Summary</h2>
            <div class="summary-stat">
                <strong>{total_pages}</strong><br>
                Total Pages
            </div>
            <div class="summary-stat">
                <strong>{successful_pages}</strong><br>
                Successful
            </div>
            <div class="summary-stat">
                <strong>{total_pages - successful_pages}</strong><br>
                Failed
            </div>
            <div class="summary-stat">
                <strong>{os.path.basename(pdf_path)}</strong><br>
                PDF File
            </div>
        </div>
        
        <h2>Processing Results</h2>
        <table>
            <tr>
                <th>Page</th>
                <th>Analyzer</th>
                <th>Visualizer</th>
                <th>Extractor</th>
                <th>Actions</th>
            </tr>
"""

    for result in results:
        page_num = result['page']

        # Determine status for each step
        analyzer_status = "✓ Success" if result['analyzer']['success'] else "✗ Failed"
        if result['analyzer'].get('skipped'):
            analyzer_status = "— Skipped"

        visualizer_status = "✓ Success" if result.get('visualizer', {}).get('success') else "✗ Failed"
        if 'visualizer' not in result:
            visualizer_status = "— Skipped"

        extractor_status = "✓ Success" if result.get('extractor', {}).get('success') else "✗ Failed"
        if 'extractor' not in result:
            extractor_status = "— Skipped"

        # Build action links
        actions = []
        if result['analyzer']['success']:
            doctags_file = result['analyzer'].get('doctags_file')
            if doctags_file:
                actions.append(f'<a href="{os.path.basename(doctags_file)}" class="page-link">DocTags</a>')

        if result.get('visualizer', {}).get('success'):
            viz_file = result['visualizer'].get('image_file')
            if viz_file:
                actions.append(f'<a href="{os.path.basename(viz_file)}" class="page-link">Visualization</a>')

        if result.get('extractor', {}).get('success'):
            extract_dir = result['extractor'].get('output_dir')
            if extract_dir:
                index_file = f"{os.path.basename(extract_dir)}/index.html"
                actions.append(f'<a href="{index_file}" class="page-link">Extracted Images</a>')

        # Determine row styling
        analyzer_class = "success" if result['analyzer']['success'] else "failed"
        if result['analyzer'].get('skipped'):
            analyzer_class = "skipped"

        visualizer_class = "success" if result.get('visualizer', {}).get('success') else "failed"
        if 'visualizer' not in result:
            visualizer_class = "skipped"

        extractor_class = "success" if result.get('extractor', {}).get('success') else "failed"
        if 'extractor' not in result:
            extractor_class = "skipped"

        html += f"""            <tr>
                <td><strong>Page {page_num}</strong></td>
                <td class="{analyzer_class}">{analyzer_status}</td>
                <td class="{visualizer_class}">{visualizer_status}</td>
                <td class="{extractor_class}">{extractor_status}</td>
                <td>{' | '.join(actions) if actions else 'No outputs'}</td>
            </tr>
"""

    html += """        </table>
    </div>
</body>
</html>
"""

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return report_path

def main():
    # Parse arguments
    args = parse_arguments()

    # Check if PDF exists
    if not os.path.exists(args.pdf):
        print(f"Error: PDF file not found: {args.pdf}")
        sys.exit(1)

    # Create results directory
    results_dir = ensure_results_folder()
    if args.output_dir != 'results':
        results_dir = Path(args.output_dir)
        if not results_dir.exists():
            results_dir.mkdir(parents=True)
            print(f"Created output directory: {results_dir}")

    # Determine which pages to process
    pages_to_process = []

    if args.pages:
        # Specific pages provided
        pages_to_process = parse_page_list(args.pages)
        print(f"Processing specific pages: {pages_to_process}")
    else:
        # Range of pages
        pdf_page_count = get_pdf_page_count(args.pdf)

        if pdf_page_count:
            print(f"PDF has {pdf_page_count} pages")

        start_page = args.start
        end_page = args.end or pdf_page_count or 1

        if args.max_pages and (end_page - start_page + 1) > args.max_pages:
            end_page = start_page + args.max_pages - 1
            print(f"Limiting to {args.max_pages} pages")

        pages_to_process = list(range(start_page, end_page + 1))
        print(f"Processing pages {start_page} to {end_page}")

    # Start batch processing
    print(f"\nStarting batch processing of {len(pages_to_process)} pages")
    print(f"PDF: {args.pdf}")
    print(f"Output directory: {results_dir}")

    if args.skip_analyzer:
        print("Note: Skipping analyzer step")
    if args.skip_visualizer:
        print("Note: Skipping visualizer step")
    if args.skip_extractor:
        print("Note: Skipping extractor step")

    # Process each page
    all_results = []
    start_time = time.time()

    for i, page_num in enumerate(pages_to_process, 1):
        print(f"\n[{i}/{len(pages_to_process)}] Processing page {page_num}")

        page_result = process_page(args.pdf, page_num, args, results_dir)
        all_results.append(page_result)

        # Save intermediate results
        with open(results_dir / "batch_results.json", 'w') as f:
            json.dump(all_results, f, indent=2)

    # Calculate processing time
    end_time = time.time()
    processing_time = end_time - start_time

    # Create summary report
    print(f"\n{'='*60}")
    print("BATCH PROCESSING COMPLETE")
    print(f"{'='*60}")
    print(f"Total pages processed: {len(pages_to_process)}")
    print(f"Total time: {processing_time:.1f} seconds")
    print(f"Average time per page: {processing_time/len(pages_to_process):.1f} seconds")

    # Create HTML report
    report_path = create_batch_report(all_results, args.pdf, results_dir)
    print(f"\nBatch report created: {report_path}")

    # Summary statistics
    successful_count = sum(1 for r in all_results if all(
        r.get(step, {}).get('success', False) or r.get(step, {}).get('skipped', False)
        for step in ['analyzer', 'visualizer', 'extractor'] if step in r
    ))

    print(f"\nSuccess rate: {successful_count}/{len(pages_to_process)} pages ({successful_count/len(pages_to_process)*100:.1f}%)")

    # Print any errors
    errors = []
    for result in all_results:
        page_num = result['page']
        for step in ['analyzer', 'visualizer', 'extractor']:
            if step in result and not result[step]['success'] and not result[step].get('skipped'):
                error = result[step].get('error', 'Unknown error')
                errors.append(f"Page {page_num} - {step}: {error}")

    if errors:
        print("\nErrors encountered:")
        for error in errors[:5]:  # Show first 5 errors
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... and {len(errors) - 5} more errors")

    print(f"\nAll results saved to: {results_dir}")

if __name__ == "__main__":
    main()