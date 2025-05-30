from flask import Flask, request, send_file, jsonify, Response
import subprocess
import os
import sys
import time
import threading
import logging
from pathlib import Path
import uuid
import pdf2image

# Add the parent directory to Python path to allow imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize Flask app with frontend folder structure
# Frontend is in the parent directory
frontend_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'frontend')
app = Flask(__name__,
            static_folder=os.path.join(frontend_path, 'static'),
            static_url_path='/static')

# Dictionary to store background task results
task_results = {}

# Import batch processor if available
try:
    from backend.batch_treatment.batch_processor import start_batch_processing, get_batch_processor, cleanup_old_batches
    batch_processing_available = True
except ImportError:
    logger.warning("batch_processor.py not found. Batch processing features will be disabled.")
    batch_processing_available = False

# Ensure results folder exists
def ensure_results_folder():
    # Always create results folder relative to where app.py is run from
    results_dir = Path.cwd() / "results"
    if not results_dir.exists():
        results_dir.mkdir()
        logger.info(f"Created results directory at: {results_dir.absolute()}")
    else:
        logger.info(f"Results directory exists at: {results_dir.absolute()}")
    return results_dir

# Ensure frontend folders exist
def ensure_frontend_folders():
    frontend_dir = Path(frontend_path)
    if not frontend_dir.exists():
        frontend_dir.mkdir()
        logger.info(f"Created frontend directory: {frontend_dir}")

    static_dir = frontend_dir / "static"
    if not static_dir.exists():
        static_dir.mkdir()
        logger.info(f"Created static directory: {static_dir}")

    return frontend_dir, static_dir

@app.route('/')
def index():
    return send_file(os.path.join(frontend_path, 'index.html'))

@app.route('/batch')
def batch_interface():
    """Serve the batch processing interface"""
    return send_file(os.path.join(frontend_path, 'batch.html'))

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(os.path.join(frontend_path, 'static', filename))

@app.route('/pdf-files')
def pdf_files():
    try:
        # Get list of PDF files in the current directory
        pdf_files = [f for f in os.listdir('.') if f.endswith('.pdf')]
        logger.info(f"Found {len(pdf_files)} PDF files")
        return jsonify(pdf_files)
    except Exception as e:
        logger.error(f"Error listing PDF files: {str(e)}")
        return jsonify({"error": str(e)}), 500

@app.route('/pdf-info/<path:pdf_file>')
def pdf_info(pdf_file):
    """Get information about a PDF file (page count, etc.)"""
    try:
        if not os.path.exists(pdf_file):
            return jsonify({'error': f'PDF file not found: {pdf_file}'}), 404

        # Get page count using pdf2image
        try:
            from pdf2image.pdf2image import pdfinfo_from_path
            info = pdfinfo_from_path(pdf_file)
            page_count = info["Pages"]
        except Exception as e:
            # Fallback method
            logger.warning(f"pdfinfo failed, using fallback: {e}")
            images = pdf2image.convert_from_path(pdf_file, dpi=72, first_page=1, last_page=1)
            page_count = 1  # At least one page if we got here

            # Try to get actual count by checking last pages
            for i in range(2, 1000):  # Reasonable upper limit
                try:
                    images = pdf2image.convert_from_path(pdf_file, dpi=72, first_page=i, last_page=i)
                    if not images:
                        page_count = i - 1
                        break
                    page_count = i
                except:
                    page_count = i - 1
                    break

        return jsonify({
            'pageCount': page_count,
            'filename': os.path.basename(pdf_file),
            'size': os.path.getsize(pdf_file)
        })

    except Exception as e:
        logger.error(f"Error getting PDF info: {str(e)}")
        return jsonify({'error': str(e)}), 500

def run_command(task_id, command):
    """Run a command in a background thread and store result"""
    logger.info(f"Running command: {command}")
    try:
        # Log the current working directory to help with debugging
        current_dir = os.getcwd()
        logger.info(f"Current working directory: {current_dir}")

        # The command already contains the full path, so we just need to verify it exists
        script_parts = command.split()
        script_path = script_parts[1]

        if not os.path.exists(script_path):
            logger.error(f"Script not found: {script_path} in {current_dir}")
            task_results[task_id] = {
                'success': False,
                'error': f"Script not found: {script_path}. Make sure all scripts are in the correct directory.",
                'done': True
            }
            return

        # Run the command with more detailed error capture
        # Important: Use pipe input to automatically answer "n" to the prompt
        # Make sure we run from the project root directory
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True,
            cwd=os.getcwd()  # Explicitly set working directory to current directory
        )

        # Send "n" to the process to bypass the "process all pages" prompt
        stdout, stderr = process.communicate(input="n\n")

        # Log the raw output for debugging
        logger.info(f"Command stdout: {stdout[:500]}...")
        if stderr:
            logger.error(f"Command stderr: {stderr}")

        # Update task result based on return code
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

        # List files in current directory to help with debugging
        files = os.listdir('.')
        logger.info(f"Files in current directory: {files}")

        # Check if PDF exists
        if not os.path.exists(pdf_file):
            logger.error(f"PDF file not found: {pdf_file}")
            return jsonify({'success': False, 'error': f'PDF file not found: {pdf_file}'}), 400

        # Check if analyzer.py exists in the new location
        analyzer_path = os.path.join('backend', 'page_treatment', 'analyzer.py')
        if not os.path.exists(analyzer_path):
            logger.error(f"analyzer.py not found at: {analyzer_path}")
            return jsonify({'success': False, 'error': 'analyzer.py not found in backend/page_treatment directory'}), 500

        # Add the --all-pages=false flag or explicitly specify the page to avoid the prompt
        command = f"python backend/page_treatment/analyzer.py --image {pdf_file} --page {page_num} --start-page {page_num} --end-page {page_num}"

        # Generate a task ID
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

        # Return the task ID immediately
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"Analyzer started. Processing {pdf_file} page {page_num}..."
        })
    except Exception as e:
        import traceback
        logger.error(f"Error starting analyzer: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/task-status/<task_id>')
def task_status(task_id):
    if task_id not in task_results:
        return jsonify({'success': False, 'error': 'Task not found'}), 404

    result = task_results[task_id].copy()  # Make a copy to avoid modifying the original

    # If task is completed, add file paths and verify they exist
    if result['done'] and result['success']:
        if task_id.startswith('analyzer_'):
            doctags_path = Path("results") / "output.doctags.txt"
            if doctags_path.exists():
                result['doctags_file'] = "results/output.doctags.txt"
            else:
                logger.warning(f"DocTags file not found: {doctags_path}")

        elif task_id.startswith('visualizer_'):
            page_num = task_id.split('_')[-1] if len(task_id.split('_')) > 2 else "1"
            viz_filename = f"visualization_page_{page_num}.png"

            # Check multiple possible locations
            possible_paths = [
                Path("results") / viz_filename,
                Path.cwd() / "results" / viz_filename,
                Path(__file__).parent.parent / "results" / viz_filename
            ]

            for path in possible_paths:
                if path.exists():
                    result['image_file'] = f"results/{viz_filename}"
                    logger.info(f"Found visualization at: {path}")
                    break
            else:
                logger.error(f"Visualization file not found in any location for page {page_num}")
                # Log what files exist in results
                results_dir = Path("results")
                if results_dir.exists():
                    files = list(results_dir.glob("*.png"))
                    logger.info(f"PNG files in results: {[f.name for f in files[:5]]}")

    return jsonify(result)

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

        # Generate a task ID
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
        logger.error(f"Error starting visualizer: {str(e)}")
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

        # Generate a task ID
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
        logger.error(f"Error starting extractor: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/results/<path:filename>')
def results(filename):
    try:
        # Always use the results directory relative to current working directory
        results_dir = Path.cwd() / "results"
        file_path = results_dir / filename

        logger.info(f"Requested file: {filename}")
        logger.info(f"Looking for file at: {file_path.absolute()}")
        logger.info(f"File exists: {file_path.exists()}")

        if file_path.exists() and file_path.is_file():
            logger.info(f"Serving file: {file_path}")
            return send_file(str(file_path.absolute()))
        else:
            logger.error(f"File not found: {file_path}")
            # List what files ARE in the results directory
            if results_dir.exists():
                files = list(results_dir.glob("*"))
                logger.info(f"Files in results directory: {[f.name for f in files[:10]]}")
            return jsonify({'error': f"File not found: {filename}"}), 404
    except Exception as e:
        logger.error(f"Error serving file {filename}: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({'error': f"Error serving file: {filename}"}), 500

@app.route('/pdf-preview/<pdf_file>/<int:page_num>')
def pdf_preview(pdf_file, page_num):
    """Generate and serve a preview image of a PDF page"""
    try:
        import pdf2image
        from PIL import Image
        import io

        # Check if PDF exists
        if not os.path.exists(pdf_file):
            return jsonify({'error': f'PDF file not found: {pdf_file}'}), 404

        # Convert PDF page to image
        logger.info(f"Generating preview for {pdf_file} page {page_num}")

        # Use moderate DPI for preview (lower than analyzer's 200)
        preview_dpi = 150

        try:
            pdf_images = pdf2image.convert_from_path(
                pdf_file,
                dpi=preview_dpi,
                first_page=page_num,
                last_page=page_num
            )

            if not pdf_images:
                return jsonify({'error': f'Could not extract page {page_num} from PDF'}), 400

            # Get the first (and only) page
            pil_image = pdf_images[0]

            # Resize if too large (max width 1200px for web preview)
            max_width = 1200
            if pil_image.width > max_width:
                ratio = max_width / pil_image.width
                new_height = int(pil_image.height * ratio)
                pil_image = pil_image.resize((max_width, new_height), Image.LANCZOS)

            # Convert to bytes
            img_io = io.BytesIO()
            pil_image.save(img_io, 'PNG', optimize=True)
            img_io.seek(0)

            return send_file(img_io, mimetype='image/png',
                             as_attachment=False,
                             download_name=f'{pdf_file}_page_{page_num}_preview.png')

        except Exception as e:
            logger.error(f"Error converting PDF to image: {str(e)}")
            return jsonify({'error': f'Error converting PDF to image: {str(e)}'}), 500

    except Exception as e:
        logger.error(f"Error generating PDF preview: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/check-environment')
def check_environment():
    """Endpoint to check the environment and available scripts"""
    try:
        # Get current directory
        current_dir = os.getcwd()

        # List all files in directory
        files = os.listdir('.')

        # Check for required scripts in new location
        backend_page_dir = os.path.join('backend', 'page_treatment')
        required_scripts = ['analyzer.py', 'visualizer.py', 'picture_extractor.py']
        missing_scripts = []

        for script in required_scripts:
            script_path = os.path.join(backend_page_dir, script)
            if not os.path.exists(script_path):
                missing_scripts.append(script)

        # Check for PDFs
        pdf_files = [f for f in files if f.endswith('.pdf')]

        # Check for results directory
        results_dir = Path("results")
        results_dir_exists = results_dir.exists()
        results_files = []

        # Try to check Python version and installed packages
        python_info = subprocess.run(['python', '--version'], capture_output=True, text=True)
        python_version = python_info.stdout.strip() if python_info.returncode == 0 else "Unknown"

        # Check if the 'results' directory exists and is writable
        results_writable = False
        if results_dir_exists:
            try:
                test_file = results_dir / "test_write.txt"
                with open(test_file, 'w') as f:
                    f.write("test")
                os.remove(test_file)
                results_writable = True

                # List files in results directory
                results_files = [f.name for f in results_dir.iterdir() if f.is_file()][:20]  # Limit to 20 files
            except:
                pass

        return jsonify({
            'cwd': current_dir,
            'files': files,
            'missing_scripts': missing_scripts,
            'pdf_files': pdf_files,
            'results_dir_exists': results_dir_exists,
            'results_dir_writable': results_writable,
            'results_files': results_files,
            'python_version': python_version,
            'batch_processing_available': batch_processing_available
        })
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return jsonify({
            'error': str(e),
            'traceback': error_details
        }), 500

@app.route('/run-manual-command', methods=['POST'])
def run_manual_command():
    """Endpoint to run a manual command for debugging purposes"""
    try:
        command = request.form.get('command')
        if not command:
            return jsonify({'success': False, 'error': 'No command specified'}), 400

        logger.info(f"Running manual command: {command}")

        # Update paths in manual commands to use backend directory only if not already present
        if 'backend/page_treatment/' not in command:
            command = command.replace('analyzer.py', 'backend/page_treatment/analyzer.py')
            command = command.replace('visualizer.py', 'backend/page_treatment/visualizer.py')
            command = command.replace('picture_extractor.py', 'backend/page_treatment/picture_extractor.py')

        try:
            # Run the command synchronously for immediate feedback
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )

            stdout, stderr = process.communicate(input="n\n", timeout=60)  # 60 second timeout

            success = process.returncode == 0
            return jsonify({
                'success': success,
                'output': stdout,
                'error': stderr,
                'returncode': process.returncode
            })
        except subprocess.TimeoutExpired:
            return jsonify({
                'success': False,
                'error': "Command timed out after 60 seconds"
            })
        except Exception as e:
            import traceback
            return jsonify({
                'success': False,
                'error': str(e),
                'traceback': traceback.format_exc()
            })
    except Exception as e:
        logger.error(f"Error running manual command: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# Batch processing endpoints
@app.route('/run-batch-processor', methods=['POST'])
def run_batch_processor():
    """Start a new batch processing job"""
    if not batch_processing_available:
        return jsonify({'success': False, 'error': 'Batch processing not available'}), 503

    try:
        pdf_file = request.form.get('pdf_file')
        start_page = int(request.form.get('start_page', 1))
        end_page = int(request.form.get('end_page', 1))

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        if not os.path.exists(pdf_file):
            return jsonify({'success': False, 'error': f'PDF file not found: {pdf_file}'}), 404

        # Processing options
        options = {
            'adjust': request.form.get('adjust') == 'true',
            'parallel': request.form.get('parallel') == 'true',
            'generate_report': request.form.get('generate_report') == 'true'
        }

        # Generate batch ID
        batch_id = str(uuid.uuid4())[:8]

        # Start batch processing
        if start_batch_processing(batch_id, pdf_file, start_page, end_page, options):
            logger.info(f"Started batch processing with ID: {batch_id}")
            return jsonify({
                'success': True,
                'batch_id': batch_id,
                'message': f'Batch processing started for {end_page - start_page + 1} pages'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to start batch processing'}), 500

    except Exception as e:
        logger.error(f"Error starting batch processor: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/batch-status/<batch_id>')
def batch_status(batch_id):
    """Get the status of a batch processing job"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        state = processor.get_state()

        # Only return recent logs (last 20)
        state['logs'] = state['logs'][-20:]

        return jsonify(state)

    except Exception as e:
        logger.error(f"Error getting batch status: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/pause-batch/<batch_id>', methods=['POST'])
def pause_batch(batch_id):
    """Pause a batch processing job"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        processor.pause()
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error pausing batch: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/resume-batch/<batch_id>', methods=['POST'])
def resume_batch(batch_id):
    """Resume a paused batch processing job"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        processor.resume()
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error resuming batch: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/cancel-batch/<batch_id>', methods=['POST'])
def cancel_batch(batch_id):
    """Cancel a batch processing job"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        processor.cancel()
        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error cancelling batch: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/retry-page', methods=['POST'])
def retry_page():
    """Retry processing a single failed page"""
    if not batch_processing_available:
        return jsonify({'success': False, 'error': 'Batch processing not available'}), 503

    try:
        pdf_file = request.form.get('pdf_file')
        page_num = int(request.form.get('page_num'))
        adjust = request.form.get('adjust') == 'true'

        if not pdf_file or not page_num:
            return jsonify({'success': False, 'error': 'Missing parameters'}), 400

        # Create a single-page batch for retry
        batch_id = f"retry_{uuid.uuid4().hex[:8]}"
        options = {'adjust': adjust, 'parallel': False, 'generate_report': False}

        if start_batch_processing(batch_id, pdf_file, page_num, page_num, options):
            # Wait for completion (since it's just one page)
            processor = get_batch_processor(batch_id)
            timeout = 60  # 60 seconds timeout
            start_time = time.time()

            while not processor.state['completed'] and (time.time() - start_time) < timeout:
                time.sleep(0.5)

            if processor.state['results']['successful'] > 0:
                return jsonify({'success': True})
            else:
                return jsonify({'success': False, 'error': 'Page processing failed'})
        else:
            return jsonify({'success': False, 'error': 'Failed to start retry'}), 500

    except Exception as e:
        logger.error(f"Error retrying page: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/download-batch-results/<batch_id>')
def download_batch_results(batch_id):
    """Download all batch results as a ZIP file"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        # Create ZIP archive
        zip_path = processor.create_zip_archive()

        if zip_path and os.path.exists(zip_path):
            return send_file(
                zip_path,
                mimetype='application/zip',
                as_attachment=True,
                download_name=f'batch_results_{batch_id}.zip'
            )
        else:
            return jsonify({'error': 'Failed to create archive'}), 500

    except Exception as e:
        logger.error(f"Error downloading batch results: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/batch-report/<batch_id>')
def batch_report(batch_id):
    """View the batch processing report"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        report_path = processor.results_dir / "report.html"

        if report_path.exists():
            # Read and modify the HTML to fix image paths
            with open(report_path, 'r') as f:
                html_content = f.read()

            # Replace relative image paths with absolute Flask routes
            html_content = html_content.replace(
                'src="visualization_page_',
                f'src="/batch-report-image/{batch_id}/visualization_page_'
            )
            html_content = html_content.replace(
                'href="visualization_page_',
                f'href="/batch-report-image/{batch_id}/visualization_page_'
            )

            return html_content
        else:
            return jsonify({'error': 'Report not found'}), 404

    except Exception as e:
        logger.error(f"Error viewing batch report: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/batch-report-image/<batch_id>/<path:filename>')
def batch_report_image(batch_id, filename):
    """Serve images from batch report directory"""
    if not batch_processing_available:
        return jsonify({'error': 'Batch processing not available'}), 503

    try:
        processor = get_batch_processor(batch_id)

        if not processor:
            return jsonify({'error': 'Batch not found'}), 404

        image_path = processor.results_dir / filename

        if image_path.exists() and image_path.is_file():
            return send_file(image_path)
        else:
            return jsonify({'error': f'Image not found: {filename}'}), 404

    except Exception as e:
        logger.error(f"Error serving batch report image: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/open-results-folder', methods=['POST'])
def open_results_folder():
    """Open the results folder in the system file explorer"""
    try:
        results_path = os.path.abspath("results")

        if sys.platform == 'darwin':  # macOS
            subprocess.run(['open', results_path])
        elif sys.platform == 'win32':  # Windows
            os.startfile(results_path)
        else:  # Linux
            subprocess.run(['xdg-open', results_path])

        return jsonify({'success': True})

    except Exception as e:
        logger.error(f"Error opening results folder: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/debug-results')
def debug_results():
    """Debug endpoint to check results directory"""
    try:
        results_info = {
            'cwd': os.getcwd(),
            'results_paths_checked': []
        }

        # Check multiple possible results locations
        possible_results_dirs = [
            Path("results"),
            Path.cwd() / "results",
            Path(__file__).parent.parent / "results"
        ]

        for results_dir in possible_results_dirs:
            dir_info = {
                'path': str(results_dir),
                'absolute_path': str(results_dir.absolute()),
                'exists': results_dir.exists(),
                'files': []
            }

            if results_dir.exists():
                try:
                    # List all files in the directory
                    files = list(results_dir.glob("*"))
                    dir_info['files'] = [f.name for f in files if f.is_file()][:20]  # Limit to 20 files
                except Exception as e:
                    dir_info['error'] = str(e)

            results_info['results_paths_checked'].append(dir_info)

        return jsonify(results_info)

    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Cleanup task for batch processors
def cleanup_task():
    """Periodic cleanup of old batch processors"""
    if not batch_processing_available:
        return

    while True:
        time.sleep(3600)  # Run every hour
        try:
            cleanup_old_batches(24)  # Clean up batches older than 24 hours
        except Exception as e:
            logger.error(f"Error in cleanup task: {str(e)}")

# Start cleanup thread when app starts (only if batch processing is available)
if batch_processing_available:
    cleanup_thread = threading.Thread(target=cleanup_task)
    cleanup_thread.daemon = True
    cleanup_thread.start()

if __name__ == '__main__':
    # Ensure folders exist
    ensure_results_folder()
    ensure_frontend_folders()

    # Check environment
    if not batch_processing_available:
        logger.warning("batch_processor.py not found. Batch processing features will be disabled.")
    else:
        logger.info("Batch processing features enabled.")

    app.run(debug=True, host='127.0.0.1', port=5000)