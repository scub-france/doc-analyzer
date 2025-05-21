from flask import Flask, request, send_file, jsonify, Response
import subprocess
import os
import time
import threading
import logging
import json
import re
from pathlib import Path
import glob
from PIL import Image
import pdf2image

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Dictionary to store background task results
task_results = {}

# Ensure results folder exists
def ensure_results_folder():
    results_dir = Path("results")
    if not results_dir.exists():
        results_dir.mkdir()
    return results_dir

@app.route('/')
def index():
    return send_file('index.html')

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

@app.route('/results/<path:filename>')
def results(filename):
    try:
        return send_file(os.path.join('results', filename))
    except Exception as e:
        logger.error(f"Error serving file {filename}: {str(e)}")
        return jsonify({'error': f"File not found: {filename}"}), 404

@app.route('/check-environment')
def check_environment():
    """Endpoint to check the environment and available scripts"""
    try:
        # Get current directory
        current_dir = os.getcwd()

        # List all files in directory
        files = os.listdir('.')

        # Check for required scripts
        required_scripts = ['analyzer.py', 'visualizer.py', 'picture_extractor.py']
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

# NEW ROUTES TO SUPPORT ENHANCED UI

@app.route('/generate-preview', methods=['POST'])
def generate_preview():
    """Generate a preview image of a PDF page"""
    try:
        # Get parameters
        pdf_file = request.form.get('pdf_file')
        page_num = int(request.form.get('page_num', 1))

        if not pdf_file or not os.path.exists(pdf_file):
            return jsonify({'success': False, 'error': 'PDF file not found'}), 400

        # Ensure results directory exists
        results_dir = ensure_results_folder()
        preview_path = results_dir / f"preview_{os.path.basename(pdf_file)}_{page_num}.png"

        # Convert PDF page to image
        try:
            # Get total page count
            from pdf2image.pdf2image import pdfinfo_from_path
            pdf_info = pdfinfo_from_path(pdf_file)
            page_count = pdf_info["Pages"]

            # Ensure the page number is valid
            if page_num > page_count:
                return jsonify({'success': False, 'error': f'Page number {page_num} exceeds total pages {page_count}'}), 400

            # Convert the page
            images = pdf2image.convert_from_path(
                pdf_file,
                dpi=150,  # Lower DPI for preview
                first_page=page_num,
                last_page=page_num
            )

            if images:
                # Resize for preview if too large
                MAX_HEIGHT = 600
                img = images[0]
                ratio = MAX_HEIGHT / img.height if img.height > MAX_HEIGHT else 1
                if ratio < 1:
                    new_width = int(img.width * ratio)
                    img = img.resize((new_width, MAX_HEIGHT), Image.Resampling.LANCZOS)

                # Save the preview
                img.save(preview_path)

                return jsonify({
                    'success': True,
                    'preview_image': f'/results/{preview_path.name}',
                    'page_count': page_count
                })
            else:
                return jsonify({'success': False, 'error': 'Failed to convert PDF page'}), 500

        except Exception as e:
            logger.error(f"Error converting PDF: {str(e)}")
            return jsonify({'success': False, 'error': str(e)}), 500

    except Exception as e:
        logger.error(f"Error generating preview: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get-doctags-content')
def get_doctags_content():
    """Get the content of a DocTags file"""
    try:
        path = request.args.get('path')
        if not path or not os.path.exists(path):
            # Try prepending 'results/' if the path doesn't exist
            if not path.startswith('results/'):
                path = f"results/{path}"

            if not os.path.exists(path):
                return "DocTags file not found", 404

        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()

        return content
    except Exception as e:
        logger.error(f"Error reading DocTags file: {str(e)}")
        return f"Error: {str(e)}", 500

@app.route('/get-extracted-images')
def get_extracted_images():
    """Get a list of extracted images for a specific PDF page"""
    try:
        pdf_file = request.args.get('pdf')
        page_num = request.args.get('page', 1)

        if not pdf_file:
            return jsonify({'success': False, 'error': 'PDF file not specified'}), 400

        # Get the base name of the PDF without extension
        pdf_basename = os.path.splitext(os.path.basename(pdf_file))[0]

        # Look for extracted images in the results/pictures directory
        pictures_dir = Path("results") / "pictures"

        if not pictures_dir.exists():
            return jsonify({'success': True, 'images': []})

        # Pattern to match: picture_*.*
        image_pattern = pictures_dir / "picture_*.png"
        image_files = glob.glob(str(image_pattern))

        images = []
        for image_file in image_files:
            img_path = Path(image_file)
            img_id = "unknown"
            img_caption = ""

            # Try to extract ID from filename (picture_1_caption.png)
            match = re.search(r'picture_(\d+)', img_path.name)
            if match:
                img_id = match.group(1)

            # Look for a matching caption file
            caption_file = img_path.with_suffix('.txt')
            if caption_file.exists():
                with open(caption_file, 'r', encoding='utf-8') as f:
                    img_caption = f.read().strip()

            images.append({
                'id': img_id,
                'path': f'/results/pictures/{img_path.name}',
                'caption': img_caption
            })

        return jsonify({'success': True, 'images': images})

    except Exception as e:
        logger.error(f"Error getting extracted images: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    ensure_results_folder()
    app.run(debug=True, host='127.0.0.1', port=5000)