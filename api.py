#!/usr/bin/env python3
"""
DocTags API - Simple API wrapper around existing DocTags scripts.

Usage:
    python api.py

This starts a Flask server on port 5000 that exposes the DocTags functionality.
"""

from flask import Flask, request, jsonify, send_file
import os
import tempfile
import subprocess
import shutil
from pathlib import Path
import threading
import time
import json
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Directory to store uploaded files and results
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Dictionary to store job status
jobs = {}


def run_analyzer(pdf_path, page_num, output_path, dpi=200, prompt="Convert this page to docling."):
    """Run analyzer.py script on a PDF page."""
    logger.info(f"Running analyzer on {pdf_path}, page {page_num}")

    cmd = [
        "python", "analyzer.py",
        "--image", pdf_path,
        "--page", str(page_num),
        "--output", output_path,
        "--dpi", str(dpi),
        "--prompt", prompt
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(f"Error running analyzer: {result.stderr}")
            return False, result.stderr

        logger.info(f"Analyzer completed successfully for page {page_num}")
        return True, output_path
    except Exception as e:
        logger.error(f"Exception running analyzer: {str(e)}")
        return False, str(e)


def run_fix_scaling(doctags_path, output_path, x_factor=0.7, y_factor=0.7):
    """Run fix_scaling.py script on DocTags file."""
    logger.info(f"Running fix_scaling on {doctags_path}")

    cmd = [
        "python", "fix_scaling.py",
        "--doctags", doctags_path,
        "--output", output_path,
        "--x-factor", str(x_factor),
        "--y-factor", str(y_factor)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(f"Error running fix_scaling: {result.stderr}")
            return False, result.stderr

        logger.info("Fix scaling completed successfully")
        return True, output_path
    except Exception as e:
        logger.error(f"Exception running fix_scaling: {str(e)}")
        return False, str(e)


def run_visualizer(doctags_path, pdf_path, page_num, output_path, adjust=True):
    """Run visualizer.py script on DocTags file."""
    logger.info(f"Running visualizer on {doctags_path}, page {page_num}")

    cmd = [
        "python", "visualizer.py",
        "--doctags", doctags_path,
        "--pdf", pdf_path,
        "--page", str(page_num),
        "--output", output_path
    ]

    if adjust:
        cmd.append("--adjust")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            logger.error(f"Error running visualizer: {result.stderr}")
            return False, result.stderr

        logger.info("Visualizer completed successfully")
        return True, output_path
    except Exception as e:
        logger.error(f"Exception running visualizer: {str(e)}")
        return False, str(e)


def count_pdf_pages(pdf_path):
    """Count the number of pages in a PDF file."""
    logger.info(f"Counting pages in {pdf_path}")

    cmd = [
        "python", "visualizer.py",
        "--pdf", pdf_path,
        "--page-count"
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)
        for line in result.stdout.split('\n'):
            if "The PDF has" in line:
                page_count = int(line.split("The PDF has")[1].split("pages")[0].strip())
                logger.info(f"PDF has {page_count} pages")
                return page_count

        logger.error("Could not determine page count")
        return 0
    except Exception as e:
        logger.error(f"Exception counting PDF pages: {str(e)}")
        return 0


def process_page(job_id, pdf_path, page_num, x_factor=0.7, y_factor=0.7, dpi=200):
    """Process a single page and update job status."""
    try:
        # Update job status
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['progress'] = 0
        jobs[job_id]['current_page'] = page_num

        # Create output directories
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        os.makedirs(result_dir, exist_ok=True)

        # Paths for intermediate files
        doctags_path = os.path.join(result_dir, f"page_{page_num}.doctags.txt")
        fixed_doctags_path = os.path.join(result_dir, f"page_{page_num}.fixed.doctags.txt")
        html_path = os.path.join(result_dir, f"page_{page_num}.html")

        # Step 1: Run analyzer
        jobs[job_id]['progress'] = 33
        jobs[job_id]['current_step'] = 'Running analyzer'
        success, result = run_analyzer(pdf_path, page_num, doctags_path, dpi)
        if not success:
            jobs[job_id]['errors'].append(f"Page {page_num}: {result}")
            return False

        # Step 2: Fix scaling
        jobs[job_id]['progress'] = 66
        jobs[job_id]['current_step'] = 'Fixing scaling'
        success, result = run_fix_scaling(doctags_path, fixed_doctags_path, x_factor, y_factor)
        if not success:
            jobs[job_id]['errors'].append(f"Page {page_num}: {result}")
            return False

        # Step 3: Visualize
        jobs[job_id]['progress'] = 90
        jobs[job_id]['current_step'] = 'Creating visualization'
        success, result = run_visualizer(fixed_doctags_path, pdf_path, page_num, html_path)
        if not success:
            jobs[job_id]['errors'].append(f"Page {page_num}: {result}")
            return False

        # Add page to successful pages
        jobs[job_id]['completed_pages'].append(page_num)
        return True

    except Exception as e:
        logger.error(f"Error processing page {page_num}: {str(e)}")
        jobs[job_id]['errors'].append(f"Page {page_num}: {str(e)}")
        return False


def process_document(job_id, pdf_path, pages, x_factor=0.7, y_factor=0.7, dpi=200):
    """Process a document (all or selected pages)."""
    try:
        total_pages = len(pages)
        jobs[job_id]['total_pages'] = total_pages

        for i, page_num in enumerate(pages):
            # Update job progress
            overall_progress = int((i / total_pages) * 100)
            jobs[job_id]['progress'] = overall_progress

            # Process the page
            process_page(job_id, pdf_path, page_num, x_factor, y_factor, dpi)

        # Create old.html to navigate between pages
        create_index_html(job_id)

        # Complete the job
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['current_step'] = 'Done'
        jobs[job_id]['end_time'] = time.time()

        # Calculate success rate
        success_rate = (len(jobs[job_id]['completed_pages']) / total_pages) * 100
        jobs[job_id]['success_rate'] = success_rate

        logger.info(f"Job {job_id} completed with {success_rate:.1f}% success rate")

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}")
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['errors'].append(str(e))

    finally:
        # Store job results
        save_job_results(job_id)


def create_index_html(job_id):
    """Create an old.html file to navigate between pages."""
    try:
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        job_info = jobs[job_id]
        pdf_name = os.path.basename(job_info['pdf_path'])

        index_path = os.path.join(result_dir, "old.html")

        # Basic HTML structure
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DocTags Results - {pdf_name}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background-color: white; padding: 20px; border-radius: 5px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        h1, h2 {{ color: #333; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 20px; margin-top: 20px; }}
        .card {{ border: 1px solid #ddd; border-radius: 5px; overflow: hidden; transition: transform 0.2s; }}
        .card:hover {{ transform: translateY(-5px); box-shadow: 0 5px 15px rgba(0,0,0,0.1); }}
        .card img {{ width: 100%; height: 200px; object-fit: cover; }}
        .card-content {{ padding: 15px; }}
        .card-title {{ margin: 0; font-size: 18px; }}
        .stats {{ background-color: #f9f9f9; padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
        .error-list {{ color: #d32f2f; margin-top: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>DocTags Processing Results</h1>
        <div class="stats">
            <h2>Job Information</h2>
            <p><strong>PDF:</strong> {pdf_name}</p>
            <p><strong>Job ID:</strong> {job_id}</p>
            <p><strong>Status:</strong> {job_info['status']}</p>
            <p><strong>Success Rate:</strong> {job_info.get('success_rate', 0):.1f}%</p>
            <p><strong>Completed Pages:</strong> {len(job_info['completed_pages'])}/{job_info['total_pages']}</p>
        </div>
"""

        # Add error section if there are errors
        if job_info['errors']:
            html += """
        <div class="error-list">
            <h2>Errors</h2>
            <ul>
"""
            for error in job_info['errors']:
                html += f"                <li>{error}</li>\n"

            html += """
            </ul>
        </div>
"""

        # Add page grid
        html += """
        <h2>Pages</h2>
        <div class="grid">
"""

        # Add cards for each completed page
        for page_num in sorted(job_info['completed_pages']):
            debug_img = f"page_{page_num}.debug.png"
            html_file = f"page_{page_num}.html"

            debug_path = os.path.join(result_dir, debug_img)
            if os.path.exists(debug_path):
                html += f"""
            <div class="card">
                <a href="{html_file}">
                    <img src="{debug_img}" alt="Page {page_num}">
                    <div class="card-content">
                        <h3 class="card-title">Page {page_num}</h3>
                    </div>
                </a>
            </div>
"""

        # Close HTML
        html += """
        </div>
    </div>
</body>
</html>
"""

        # Write the HTML to file
        with open(index_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"Created old.html for job {job_id}")

    except Exception as e:
        logger.error(f"Error creating old.html: {str(e)}")


def save_job_results(job_id):
    """Save job results to a JSON file."""
    try:
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        job_info = jobs[job_id].copy()

        # Remove non-serializable items if any
        for key in ['thread']:
            if key in job_info:
                del job_info[key]

        # Save job info
        with open(os.path.join(result_dir, "job_info.json"), 'w') as f:
            json.dump(job_info, f, indent=2)

        logger.info(f"Saved job results for {job_id}")

    except Exception as e:
        logger.error(f"Error saving job results: {str(e)}")


# API Endpoints

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    """Upload a PDF file."""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400

        file = request.files['file']

        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400

        if not file.filename.lower().endswith('.pdf'):
            return jsonify({'error': 'File must be a PDF'}), 400

        # Generate unique ID for this job
        job_id = str(int(time.time()))

        # Create a directory for this job
        upload_dir = os.path.join(UPLOAD_FOLDER, job_id)
        os.makedirs(upload_dir, exist_ok=True)

        # Save the file
        file_path = os.path.join(upload_dir, file.filename)
        file.save(file_path)

        # Count pages
        page_count = count_pdf_pages(file_path)

        if page_count == 0:
            return jsonify({'error': 'Could not determine page count or PDF has no pages'}), 400

        # Create job entry
        jobs[job_id] = {
            'id': job_id,
            'pdf_path': file_path,
            'file_name': file.filename,
            'page_count': page_count,
            'status': 'uploaded',
            'start_time': time.time(),
            'end_time': None,
            'progress': 0,
            'current_step': 'Upload completed',
            'current_page': 0,
            'total_pages': 0,
            'completed_pages': [],
            'errors': []
        }

        logger.info(f"PDF uploaded: {file.filename}, job ID: {job_id}, pages: {page_count}")

        return jsonify({
            'job_id': job_id,
            'file_name': file.filename,
            'page_count': page_count,
            'status': 'uploaded'
        })

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_pdf():
    """Process a PDF file."""
    try:
        data = request.json
        job_id = data.get('job_id')

        if not job_id or job_id not in jobs:
            return jsonify({'error': 'Invalid job ID'}), 400

        job = jobs[job_id]

        # Get parameters
        pages = data.get('pages', list(range(1, job['page_count'] + 1)))
        x_factor = float(data.get('x_factor', 0.7))
        y_factor = float(data.get('y_factor', 0.7))
        dpi = int(data.get('dpi', 200))

        # Validate pages
        valid_pages = []
        for page in pages:
            if 1 <= page <= job['page_count']:
                valid_pages.append(page)

        if not valid_pages:
            return jsonify({'error': 'No valid pages selected'}), 400

        # Update job status
        job['status'] = 'queued'

        # Start processing in a background thread
        job['thread'] = threading.Thread(
            target=process_document,
            args=(job_id, job['pdf_path'], valid_pages, x_factor, y_factor, dpi)
        )
        job['thread'].daemon = True
        job['thread'].start()

        logger.info(f"Started processing job {job_id} with {len(valid_pages)} pages")

        return jsonify({
            'job_id': job_id,
            'status': 'processing',
            'pages': valid_pages
        })

    except Exception as e:
        logger.error(f"Error processing PDF: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/jobs/<job_id>', methods=['GET'])
def get_job_status(job_id):
    """Get the status of a job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]

    # Return job status without thread object
    job_status = {k: v for k, v in job.items() if k != 'thread'}

    return jsonify(job_status)


@app.route('/api/jobs', methods=['GET'])
def list_jobs():
    """List all jobs."""
    job_list = []
    for job_id, job in jobs.items():
        job_list.append({
            'id': job_id,
            'file_name': job.get('file_name', ''),
            'status': job.get('status', ''),
            'progress': job.get('progress', 0),
            'page_count': job.get('page_count', 0)
        })

    return jsonify({'jobs': job_list})


@app.route('/api/results/<job_id>', methods=['GET'])
def get_job_results(job_id):
    """Get the results of a job."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    result_dir = os.path.join(RESULTS_FOLDER, job_id)
    if not os.path.exists(result_dir):
        return jsonify({'error': 'Results not found'}), 404

    # Get a list of all files in the results directory
    files = []
    for filename in os.listdir(result_dir):
        file_path = os.path.join(result_dir, filename)
        if os.path.isfile(file_path):
            files.append({
                'name': filename,
                'size': os.path.getsize(file_path),
                'url': f'/api/results/{job_id}/files/{filename}'
            })

    return jsonify({
        'job_id': job_id,
        'files': files
    })


@app.route('/api/results/<job_id>/files/<filename>', methods=['GET'])
def get_result_file(job_id, filename):
    """Get a specific result file."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    file_path = os.path.join(RESULTS_FOLDER, job_id, filename)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found'}), 404

    return send_file(file_path)


@app.route('/api/results/<job_id>/view', methods=['GET'])
def view_results(job_id):
    """Redirect to the old.html file for viewing results."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    index_path = os.path.join(RESULTS_FOLDER, job_id, "old.html")
    if not os.path.exists(index_path):
        return jsonify({'error': 'Results not found'}), 404

    return send_file(index_path)


@app.route('/api/scale-test', methods=['POST'])
def run_scale_test():
    """Run scale test to find optimal scaling factors."""
    try:
        data = request.json
        job_id = data.get('job_id')
        page = int(data.get('page', 1))

        if not job_id or job_id not in jobs:
            return jsonify({'error': 'Invalid job ID'}), 400

        job = jobs[job_id]

        # Validate page
        if page < 1 or page > job['page_count']:
            return jsonify({'error': f'Invalid page number: {page}'}), 400

        # Create a new job ID for the scale test
        scale_job_id = f"{job_id}_scale_test"

        # Run the scale test script
        cmd = [
            "bash", "find_optimal_scale.sh",
            "-f", job['pdf_path'],
            "-p", str(page),
            "--min-x", str(data.get('min_x', 0.1)),
            "--max-x", str(data.get('max_x', 1.5)),
            "--min-y", str(data.get('min_y', 0.1)),
            "--max-y", str(data.get('max_y', 1.5)),
            "--steps", str(data.get('steps', 5))
        ]

        logger.info(f"Running scale test for job {job_id}, page {page}")

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        stdout, stderr = process.communicate()

        if process.returncode != 0:
            logger.error(f"Scale test failed: {stderr}")
            return jsonify({'error': f'Scale test failed: {stderr}'}), 500

        # Find the output directory
        pdf_basename = os.path.splitext(os.path.basename(job['pdf_path']))[0]
        scale_test_dir = f"{pdf_basename}_scale_test"

        # Copy results to our results folder
        if os.path.exists(scale_test_dir):
            target_dir = os.path.join(RESULTS_FOLDER, scale_job_id)
            if os.path.exists(target_dir):
                shutil.rmtree(target_dir)
            shutil.copytree(scale_test_dir, target_dir)

            # Create job entry for the scale test
            jobs[scale_job_id] = {
                'id': scale_job_id,
                'pdf_path': job['pdf_path'],
                'file_name': job['file_name'],
                'page_count': 1,
                'status': 'completed',
                'start_time': time.time(),
                'end_time': time.time(),
                'progress': 100,
                'current_step': 'Scale test completed',
                'current_page': page,
                'total_pages': 1,
                'completed_pages': [page],
                'errors': [],
                'parent_job_id': job_id,
                'is_scale_test': True
            }

            logger.info(f"Scale test completed for job {job_id}, created new job {scale_job_id}")

            return jsonify({
                'job_id': scale_job_id,
                'status': 'completed',
                'view_url': f'/api/results/{scale_job_id}/view'
            })
        else:
            return jsonify({'error': 'Scale test output not found'}), 500

    except Exception as e:
        logger.error(f"Error running scale test: {str(e)}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/params', methods=['GET'])
def get_default_params():
    """Get default parameters."""
    return jsonify({
        'x_factor': 0.7,
        'y_factor': 0.7,
        'dpi': 200
    })


if __name__ == '__main__':
    print("DocTags API starting on http://localhost:5000")
    print("Use the following endpoints:")
    print("  - POST /api/upload: Upload a PDF file")
    print("  - POST /api/process: Process a PDF file")
    print("  - GET /api/jobs/<job_id>: Get job status")
    print("  - GET /api/results/<job_id>: Get job results")
    print("  - GET /api/results/<job_id>/view: View job results")
    app.run(debug=True, host='0.0.0.0')