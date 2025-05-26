from flask import Flask, request, send_file, jsonify, Response
import subprocess
import os
import time
import threading
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static')

# Dictionary to store background task results
task_results = {}

# Ensure results folder exists
def ensure_results_folder():
    results_dir = Path("results")
    if not results_dir.exists():
        results_dir.mkdir()
    return results_dir

# Ensure static folder exists
def ensure_static_folder():
    static_dir = Path("static")
    if not static_dir.exists():
        static_dir.mkdir()
        logger.info(f"Created static directory: {static_dir}")
    return static_dir

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_file(os.path.join('static', filename))

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

def run_command(task_id, command):
    """Run a command in a background thread and store result"""
    logger.info(f"Running command: {command}")
    try:
        # Log the current working directory to help with debugging
        current_dir = os.getcwd()
        logger.info(f"Current working directory: {current_dir}")

        # Check if the script exists
        script_name = command.split()[1]
        if not os.path.exists(script_name):
            logger.error(f"Script not found: {script_name} in {current_dir}")
            task_results[task_id] = {
                'success': False,
                'error': f"Script not found: {script_name}. Make sure all scripts are in the same directory as app.py.",
                'done': True
            }
            return

        # Run the command with more detailed error capture
        # Important: Use pipe input to automatically answer "n" to the prompt
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True
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

        # Check if analyzer.py exists
        if not os.path.exists('analyzer.py'):
            logger.error("analyzer.py not found in current directory")
            return jsonify({'success': False, 'error': 'analyzer.py not found in current directory'}), 500

        # Add the --all-pages=false flag or explicitly specify the page to avoid the prompt
        command = f"python analyzer.py --image {pdf_file} --page {page_num} --start-page {page_num} --end-page {page_num}"

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

    result = task_results[task_id]

    # If task is completed, add file paths
    if result['done'] and result['success']:
        if task_id.startswith('analyzer_'):
            result['doctags_file'] = f"results/output.doctags.txt"
        elif task_id.startswith('visualizer_'):
            page_num = task_id.split('_')[-1] if len(task_id.split('_')) > 2 else "1"
            result['image_file'] = f"results/visualization_page_{page_num}.png"

    return jsonify(result)

@app.route('/run-visualizer', methods=['POST'])
def run_visualizer():
    try:
        pdf_file = request.form.get('pdf_file')
        page_num = request.form.get('page_num', 1)
        adjust = request.form.get('adjust') == 'true'

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        command = f"python visualizer.py --doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}"
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

        command = f"python picture_extractor.py --doctags results/output.doctags.txt --pdf {pdf_file} --page {page_num}"
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

@app.route('/run-batch', methods=['POST'])
def run_batch():
    """Run batch processing for multiple pages"""
    try:
        pdf_file = request.form.get('pdf_file')
        adjust = request.form.get('adjust') == 'true'
        batch_start = request.form.get('batch_start', '1')
        batch_end = request.form.get('batch_end', '')
        batch_pages = request.form.get('batch_pages', '')

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        # Check if PDF exists
        if not os.path.exists(pdf_file):
            logger.error(f"PDF file not found: {pdf_file}")
            return jsonify({'success': False, 'error': f'PDF file not found: {pdf_file}'}), 400

        # Check if batch_processor.py exists
        if not os.path.exists('batch_processor.py'):
            logger.error("batch_processor.py not found in current directory")
            return jsonify({'success': False, 'error': 'batch_processor.py not found in current directory'}), 500

        # Build the command
        command = f"python batch_processor.py --pdf {pdf_file}"

        if batch_pages:
            # Specific pages provided
            command += f" --pages \"{batch_pages}\""
            # Try to count the pages for progress tracking
            pages = []
            for part in batch_pages.split(','):
                part = part.strip()
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        pages.extend(range(start, end + 1))
                    except:
                        pass
                else:
                    try:
                        pages.append(int(part))
                    except:
                        pass
            total_pages = len(set(pages))
        else:
            # Page range
            command += f" --start {batch_start}"
            if batch_end:
                command += f" --end {batch_end}"
                total_pages = int(batch_end) - int(batch_start) + 1
            else:
                # Try to get PDF page count
                try:
                    from pdf2image.pdf2image import pdfinfo_from_path
                    info = pdfinfo_from_path(pdf_file)
                    pdf_pages = info["Pages"]
                    total_pages = pdf_pages - int(batch_start) + 1
                except:
                    total_pages = 1  # Default if we can't determine

        if adjust:
            command += " --adjust"

        # Generate a task ID
        task_id = f"batch_{int(time.time())}"

        # Initialize task result with progress tracking
        task_results[task_id] = {
            'success': None,
            'output': "Starting batch processing...",
            'done': False,
            'progress': {
                'total': total_pages,
                'completed': 0,
                'current_page': int(batch_start),
                'completed_pages': []
            }
        }

        # Start background thread with progress monitoring
        thread = threading.Thread(target=run_batch_command_with_progress, args=(task_id, command, total_pages))
        thread.daemon = True
        thread.start()

        # Return the task ID immediately
        return jsonify({
            'success': True,
            'task_id': task_id,
            'message': f"Batch processing started for {total_pages} pages...",
            'total_pages': total_pages
        })
    except Exception as e:
        import traceback
        logger.error(f"Error starting batch processing: {str(e)}")
        logger.error(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500

def run_batch_command_with_progress(task_id, command, total_pages):
    """Run batch command and monitor progress"""
    logger.info(f"Running batch command: {command}")
    try:
        # Run the command with real-time output capture
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
            bufsize=1
        )

        output_lines = []
        completed_pages = []
        current_page = 1

        # Read output line by line
        for line in process.stdout:
            output_lines.append(line)

            # Parse progress from output
            if "Processing page" in line:
                try:
                    # Extract page number from lines like "[1/10] Processing page 5"
                    import re
                    match = re.search(r'Processing page (\d+)', line)
                    if match:
                        current_page = int(match.group(1))

                    # Update progress
                    task_results[task_id]['progress']['current_page'] = current_page
                except:
                    pass

            elif "✓" in line and "completed for page" in line:
                try:
                    # Extract completed page number
                    import re
                    match = re.search(r'page (\d+)', line)
                    if match:
                        page_num = int(match.group(1))
                        if page_num not in completed_pages:
                            completed_pages.append(page_num)
                            task_results[task_id]['progress']['completed'] = len(completed_pages)
                            task_results[task_id]['progress']['completed_pages'] = sorted(completed_pages)
                except:
                    pass

        process.wait()

        # Get final output
        full_output = ''.join(output_lines)

        # Check if batch report was created
        report_file = None
        if "Batch report created:" in full_output:
            try:
                import re
                match = re.search(r'Batch report created: (.+)', full_output)
                if match:
                    report_path = match.group(1).strip()
                    # Convert to relative path for web access
                    if os.path.exists(report_path):
                        report_file = report_path.replace('\\', '/')
            except:
                pass

        # Extract summary
        summary = None
        if "Success rate:" in full_output:
            try:
                import re
                match = re.search(r'Success rate: (.+)', full_output)
                if match:
                    summary = match.group(1).strip()
            except:
                pass

        # Update task result
        if process.returncode == 0:
            task_results[task_id] = {
                'success': True,
                'output': full_output,
                'done': True,
                'report_file': report_file,
                'summary': summary
            }
            logger.info(f"Batch processing completed successfully: {task_id}")
        else:
            task_results[task_id] = {
                'success': False,
                'error': f"Batch processing failed with return code {process.returncode}",
                'output': full_output,
                'done': True
            }
            logger.error(f"Batch processing failed: {task_id}")

    except Exception as e:
        import traceback
        logger.error(f"Unexpected error in batch processing: {task_id} - {str(e)}")
        logger.error(traceback.format_exc())
        task_results[task_id] = {
            'success': False,
            'error': f"Exception: {str(e)}",
            'done': True
        }

@app.route('/results/<path:filename>')
def results(filename):
    try:
        file_path = os.path.join('results', filename)
        if os.path.exists(file_path):
            return send_file(file_path)
        else:
            logger.error(f"File not found: {file_path}")
            return jsonify({'error': f"File not found: {filename}"}), 404
    except Exception as e:
        logger.error(f"Error serving file {filename}: {str(e)}")
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

        # Check for required scripts
        required_scripts = ['analyzer.py', 'visualizer.py', 'picture_extractor.py', 'batch_processor.py']
        missing_scripts = [script for script in required_scripts if script not in files]

        # Check for PDFs
        pdf_files = [f for f in files if f.endswith('.pdf')]

        # Check for results directory
        results_dir = Path("results")
        results_dir_exists = results_dir.exists()

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
            except:
                pass

        return jsonify({
            'cwd': current_dir,
            'files': files,
            'missing_scripts': missing_scripts,
            'pdf_files': pdf_files,
            'results_dir_exists': results_dir_exists,
            'results_dir_writable': results_writable,
            'python_version': python_version
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

if __name__ == '__main__':
    # Ensure folders exist
    ensure_results_folder()
    ensure_static_folder()
    app.run(debug=True, host='127.0.0.1', port=5000)