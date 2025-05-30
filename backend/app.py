#!/usr/bin/env python3
"""
Flask application for DocTags web interface
"""

from flask import Flask, request, send_file, jsonify
import subprocess
import os
import sys
import time
import threading
import logging
from pathlib import Path
import uuid

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.utils import (ensure_results_folder, count_pdf_pages,
                           run_command_with_timeout, format_duration)
from backend.config import (HOST, PORT, MAX_CONTENT_LENGTH, ALLOWED_EXTENSIONS,
                            PREVIEW_DPI, PROCESSING_TIMEOUT, CLEANUP_INTERVAL,
                            CLEANUP_AGE_HOURS)
from backend.multipart_handler import default_handler

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app
frontend_path = Path(__file__).parent.parent / 'frontend'
app = Flask(__name__,
            static_folder=frontend_path / 'static',
            static_url_path='/static')

app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

# Task results storage
task_results = {}

# Import batch processor if available
try:
    from backend.batch_treatment.batch_processor import (
        start_batch_processing, get_batch_processor, cleanup_old_batches
    )
    batch_processing_available = True
except ImportError:
    logger.warning("Batch processing not available")
    batch_processing_available = False

# Ensure required directories exist
ensure_results_folder()

# Routes
@app.route('/')
def index():
    return send_file(frontend_path / 'index.html')

@app.route('/batch')
def batch_interface():
    return send_file(frontend_path / 'batch.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(frontend_path / 'static' / filename)

@app.route('/pdf-files')
def pdf_files():
    try:
        pdf_files = [f for f in os.listdir('.') if f.endswith('.pdf')]
        logger.info(f"Found {len(pdf_files)} PDF files")
        return jsonify(pdf_files)
    except Exception as e:
        logger.error(f"Error listing PDF files: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/pdf-info/<path:pdf_file>')
def pdf_info(pdf_file):
    """Get information about a PDF file"""
    try:
        if not os.path.exists(pdf_file):
            return jsonify({'error': f'PDF file not found: {pdf_file}'}), 404

        page_count = count_pdf_pages(pdf_file)
        return jsonify({
            'pageCount': page_count,
            'filename': os.path.basename(pdf_file),
            'size': os.path.getsize(pdf_file)
        })
    except Exception as e:
        logger.error(f"Error getting PDF info: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/pdf-preview/<pdf_file>/<int:page_num>')
def pdf_preview(pdf_file, page_num):
    """Generate and serve a preview image of a PDF page"""
    try:
        import pdf2image
        from PIL import Image
        import io

        if not os.path.exists(pdf_file):
            return jsonify({'error': f'PDF file not found: {pdf_file}'}), 404

        logger.info(f"Generating preview for {pdf_file} page {page_num}")

        # Convert PDF page to image
        pdf_images = pdf2image.convert_from_path(
            pdf_file, dpi=PREVIEW_DPI,
            first_page=page_num, last_page=page_num
        )

        if not pdf_images:
            return jsonify({'error': f'Could not extract page {page_num}'}), 400

        pil_image = pdf_images[0]

        # Resize if too large
        max_width = 1200
        if pil_image.width > max_width:
            ratio = max_width / pil_image.width
            new_height = int(pil_image.height * ratio)
            pil_image = pil_image.resize((max_width, new_height), Image.LANCZOS)

        # Convert to bytes
        img_io = io.BytesIO()
        pil_image.save(img_io, 'PNG', optimize=True)
        img_io.seek(0)

        return send_file(img_io, mimetype='image/png')

    except Exception as e:
        logger.error(f"Error generating PDF preview: {e}")
        return jsonify({'error': str(e)}), 500

def run_command(task_id, command):
    """Run a command in a background thread and store result"""
    logger.info(f"Running command: {command}")
    try:
        # Run the command with pipe input to automatically answer "n" to prompts
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
        )

        # Send "n" to the process to bypass prompts
        stdout, stderr = process.communicate(input="n\n")

        # Log output for debugging
        logger.info(f"Command stdout: {stdout[:500]}...")
        if stderr:
            logger.error(f"Command stderr: {stderr}")

        # Update task result
        if process.returncode == 0:
            task_results[task_id] = {
                'success': True,
                'output': stdout,
                'done': True
            }
            logger.info(f"Command completed successfully: {task_id}")
        else:
            error_message = stderr or f"Command failed with return code {process.returncode}"
            task_results[task_id] = {
                'success': False,
                'error': error_message,
                'done': True
            }
            logger.error(f"Command failed: {task_id} - {error_message}")

    except Exception as e:
        import traceback
        logger.error(f"Unexpected error: {task_id} - {str(e)}")
        logger.error(traceback.format_exc())
        task_results[task_id] = {
            'success': False,
            'error': f"Exception: {str(e)}",
            'done': True
        }

@app.route('/run-analyzer', methods=['POST'])
def run_analyzer():
    try:
        pdf_file = request.form.get('pdf_file')
        page_num = request.form.get('page_num', 1)

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        if not os.path.exists(pdf_file):
            return jsonify({'success': False, 'error': f'PDF file not found: {pdf_file}'}), 404

        command = f"python backend/page_treatment/analyzer.py --image {pdf_file} --page {page_num} --start-page {page_num} --end-page {page_num}"

        # Generate task ID
        task_id = f"analyzer_{int(time.time())}"

        # Initialize task result
        task_results[task_id] = {
            'success': None,
            'output': "Running analyzer...",
            'done': False
        }

        # Start background thread
        thread = threading.Thread(target=run_command, args=(task_id, command))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"Analyzer started. Processing {pdf_file} page {page_num}..."
        })

    except Exception as e:
        logger.error(f"Error starting analyzer: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/run-visualizer', methods=['POST'])
def run_visualizer():
    try:
        pdf_file = request.form.get('pdf_file')
        page_num = request.form.get('page_num', 1)
        adjust = request.form.get('adjust') == 'true'

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        command = f"python backend/page_treatment/visualizer.py --doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}"
        if adjust:
            command += " --adjust"

        # Generate task ID with page number
        task_id = f"visualizer_{int(time.time())}_{page_num}"

        # Initialize task result
        task_results[task_id] = {
            'success': None,
            'output': "Running visualizer...",
            'done': False
        }

        # Start background thread
        thread = threading.Thread(target=run_command, args=(task_id, command))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"Visualizer started. Processing {pdf_file} page {page_num}..."
        })

    except Exception as e:
        logger.error(f"Error starting visualizer: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/run-extractor', methods=['POST'])
def run_extractor():
    try:
        pdf_file = request.form.get('pdf_file')
        page_num = request.form.get('page_num', 1)
        adjust = request.form.get('adjust') == 'true'

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        command = f"python backend/page_treatment/picture_extractor.py --doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}"
        if adjust:
            command += " --adjust"

        # Generate task ID with page number
        task_id = f"extractor_{int(time.time())}_{page_num}"

        # Initialize task result
        task_results[task_id] = {
            'success': None,
            'output': "Running picture extractor...",
            'done': False
        }

        # Start background thread
        thread = threading.Thread(target=run_command, args=(task_id, command))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"Picture extractor started. Processing {pdf_file} page {page_num}..."
        })

    except Exception as e:
        logger.error(f"Error starting extractor: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def run_processing_task(task_type, form_data):
    """Generic function to run processing tasks"""
    try:
        pdf_file = form_data.get('pdf_file')
        page_num = form_data.get('page_num', '1')

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        if not os.path.exists(pdf_file):
            return jsonify({'success': False, 'error': f'PDF file not found: {pdf_file}'}), 404

        # Build command based on task type
        command = build_command(task_type, pdf_file, page_num, form_data)

        # Generate task ID with page number
        task_id = f"{task_type}_{int(time.time() * 1000)}_{page_num}"

        # Initialize task result
        with task_lock:
            task_results[task_id] = {
                'success': None,
                'output': f"Running {task_type}...",
                'done': False
            }

        logger.info(f"Created task {task_id} for {task_type} on page {page_num}")

        # Start background thread
        thread = threading.Thread(target=run_background_task, args=(task_id, command))
        thread.daemon = True
        thread.start()

        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"{task_type.capitalize()} started for {pdf_file} page {page_num}"
        })

    except Exception as e:
        logger.error(f"Error starting {task_type}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500

def build_command(task_type, pdf_file, page_num, form_data):
    """Build command for different task types"""
    adjust = form_data.get('adjust') == 'true'

    if task_type == 'analyzer':
        return (f"python backend/page_treatment/analyzer.py --image {pdf_file} "
                f"--page {page_num} --start-page {page_num} --end-page {page_num}")

    elif task_type == 'visualizer':
        cmd = (f"python backend/page_treatment/visualizer.py "
               f"--doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}")
        if adjust:
            cmd += " --adjust"
        return cmd

    elif task_type == 'extractor':
        cmd = (f"python backend/page_treatment/picture_extractor.py "
               f"--doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}")
        if adjust:
            cmd += " --adjust"
        return cmd

    else:
        raise ValueError(f"Unknown task type: {task_type}")

@app.route('/task-status/<task_id>')
def task_status(task_id):
    if task_id not in task_results:
        logger.warning(f"Task {task_id} not found in task_results")
        return jsonify({'success': False, 'error': 'Task not found'}), 404

    result = task_results[task_id].copy()

    # Log the complete result for debugging
    logger.info(f"Task {task_id} result: {result}")

    # If task is completed successfully, add file paths
    if result.get('done') and result.get('success'):
        if task_id.startswith('analyzer_'):
            doctags_path = Path("results") / "output.doctags.txt"
            if doctags_path.exists():
                result['doctags_file'] = "results/output.doctags.txt"
                logger.info(f"Added doctags_file to result")
            else:
                logger.warning(f"DocTags file not found: {doctags_path}")

        elif task_id.startswith('visualizer_'):
            # Extract page number from the end of task_id if it exists
            page_num = task_id.split('_')[-1] if len(task_id.split('_')) > 2 else "1"
            viz_filename = f"visualization_page_{page_num}.png"
            result['image_file'] = f"results/{viz_filename}"
            logger.info(f"Found visualization at: {result['image_file']}")

    return jsonify(result)

@app.route('/results/<path:filename>')
def serve_results(filename):
    """Serve files from results directory"""
    try:
        results_dir = ensure_results_folder()
        file_path = results_dir / filename

        if file_path.exists() and file_path.is_file():
            return send_file(file_path)
        else:
            logger.error(f"File not found: {file_path}")
            return jsonify({'error': f"File not found: {filename}"}), 404

    except Exception as e:
        logger.error(f"Error serving file {filename}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/check-environment')
def check_environment():
    """Check system environment and configuration"""
    try:
        import subprocess

        # Check for required scripts
        required_scripts = ['analyzer.py', 'visualizer.py', 'picture_extractor.py']
        backend_dir = Path('backend/page_treatment')
        missing_scripts = [s for s in required_scripts if not (backend_dir / s).exists()]

        # Get Python version
        result = subprocess.run(['python', '--version'], capture_output=True, text=True)
        python_version = result.stdout.strip() if result.returncode == 0 else "Unknown"

        # Check results directory
        results_dir = ensure_results_folder()

        return jsonify({
            'cwd': os.getcwd(),
            'files': os.listdir('.')[:50],  # Limit to 50 files
            'missing_scripts': missing_scripts,
            'pdf_files': [f for f in os.listdir('.') if f.endswith('.pdf')],
            'results_dir_exists': results_dir.exists(),
            'results_dir_writable': os.access(results_dir, os.W_OK),
            'python_version': python_version,
            'batch_processing_available': batch_processing_available
        })

    except Exception as e:
        logger.error(f"Error checking environment: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/run-manual-command', methods=['POST'])
def run_manual_command():
    """Run a manual command for debugging"""
    try:
        command = request.form.get('command')
        if not command:
            return jsonify({'success': False, 'error': 'No command specified'}), 400

        logger.info(f"Running manual command: {command}")

        # Update paths in command if needed
        if 'backend/page_treatment/' not in command:
            for script in ['analyzer.py', 'visualizer.py', 'picture_extractor.py']:
                command = command.replace(script, f'backend/page_treatment/{script}')

        success, stdout, stderr = run_command_with_timeout(command, 60)

        return jsonify({
            'success': success,
            'output': stdout,
            'error': stderr
        })

    except Exception as e:
        logger.error(f"Error running manual command: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Batch processing endpoints
if batch_processing_available:
    @app.route('/run-batch-processor', methods=['POST'])
    def run_batch_processor():
        """Start batch processing job"""
        try:
            pdf_file = request.form.get('pdf_file')
            start_page = int(request.form.get('start_page', 1))
            end_page = int(request.form.get('end_page', 1))

            if not pdf_file or not os.path.exists(pdf_file):
                return jsonify({'success': False, 'error': 'Invalid PDF file'}), 400

            # Check if there's already an active batch for this PDF
            from backend.batch_treatment.batch_processor import batch_processors, batch_lock
            with batch_lock:
                for batch_id, processor in batch_processors.items():
                    if (processor.pdf_file == pdf_file and
                            not processor.state['completed'] and
                            not processor.state['cancelled']):
                        return jsonify({
                            'success': False,
                            'error': 'A batch process is already running for this PDF',
                            'existing_batch_id': batch_id
                        }), 409

            options = {
                'adjust': request.form.get('adjust') == 'true',
                'parallel': request.form.get('parallel') == 'true',
                'generate_report': request.form.get('generate_report') == 'true'
            }

            batch_id = str(uuid.uuid4())[:8]

            if start_batch_processing(batch_id, pdf_file, start_page, end_page, options):
                return jsonify({
                    'success': True,
                    'batch_id': batch_id,
                    'message': f'Started processing {end_page - start_page + 1} pages'
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to start'}), 500

        except Exception as e:
            logger.error(f"Error starting batch: {e}")
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/batch-status/<batch_id>')
    def batch_status(batch_id):
        """Get batch processing status"""
        processor = get_batch_processor(batch_id)
        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        state = processor.get_state()
        state['logs'] = state['logs'][-20:]  # Last 20 logs only
        return jsonify(state)

# API endpoints for file upload
@app.route('/api/upload/doctags', methods=['POST'])
def api_upload_doctags():
    """Simple API endpoint for getting DocTags from uploaded PDF"""
    uploaded_file_path = None

    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'No file provided'}), 400

        file = request.files['file']
        success, result = default_handler.save_uploaded_file(file, permanent=True)

        if not success:
            return jsonify({'success': False, 'error': result.get('error')}), 400

        uploaded_file_path = result['filepath']
        page_num = request.form.get('page_num', '1')

        # Run analyzer
        command = (f"python backend/page_treatment/analyzer.py --image {uploaded_file_path} "
                   f"--page {page_num} --start-page {page_num} --end-page {page_num}")

        success, stdout, stderr = run_command_with_timeout(command, 60, "n\n")

        if not success:
            return jsonify({'success': False, 'error': 'Analysis failed', 'details': stderr}), 500

        # Read doctags
        doctags_path = ensure_results_folder() / "output.doctags.txt"
        if not doctags_path.exists():
            return jsonify({'success': False, 'error': 'DocTags not generated'}), 500

        with open(doctags_path, 'r', encoding='utf-8') as f:
            doctags_content = f.read()

        return jsonify({
            'success': True,
            'filename': result['filename'],
            'page': int(page_num),
            'doctags': doctags_content
        })

    except Exception as e:
        logger.error(f"Error in api_upload_doctags: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

    finally:
        # Cleanup uploaded file
        if uploaded_file_path and os.path.exists(uploaded_file_path):
            try:
                os.remove(uploaded_file_path)
                logger.info(f"Cleaned up: {uploaded_file_path}")
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

# Cleanup task
def cleanup_old_files():
    """Periodic cleanup of old files"""
    while True:
        time.sleep(CLEANUP_INTERVAL)
        try:
            # Cleanup uploaded files
            removed = default_handler.cleanup_old_files(CLEANUP_AGE_HOURS, 'both')
            if removed > 0:
                logger.info(f"Cleaned up {removed} old files")

            # Cleanup old tasks
            with task_lock:
                cutoff_time = time.time() - (CLEANUP_AGE_HOURS * 3600)
                old_tasks = [tid for tid, result in task_results.items()
                             if result.get('done') and tid.split('_')[1] < str(int(cutoff_time * 1000))]
                for tid in old_tasks:
                    del task_results[tid]
                if old_tasks:
                    logger.info(f"Cleaned up {len(old_tasks)} old tasks")

            # Cleanup batch processors if available
            if batch_processing_available:
                cleanup_old_batches(CLEANUP_AGE_HOURS)

        except Exception as e:
            logger.error(f"Cleanup error: {e}")

# Start cleanup thread
cleanup_thread = threading.Thread(target=cleanup_old_files)
cleanup_thread.daemon = True
cleanup_thread.start()

if __name__ == '__main__':
    logger.info(f"Starting DocTags server on {HOST}:{PORT}")
    app.run(debug=True, host=HOST, port=PORT)