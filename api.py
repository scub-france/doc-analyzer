"""
DocTags API - Direct implementation with robust process management to prevent hangs
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
import glob
import signal
import select
import resource
from werkzeug.utils import secure_filename
from flask_cors import CORS
import traceback
import sys
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Directory to store uploaded files and results
UPLOAD_FOLDER = 'uploads'
RESULTS_FOLDER = 'results'

# Create directories if they don't exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Dictionary to store job status
jobs = {}

# Maximum processing time per page (in seconds)
MAX_PAGE_PROCESSING_TIME = 300  # 5 minutes

# Function to set resource limits for child processes
def set_process_limits():
    """Set resource limits for child processes to prevent runaway memory usage"""
    try:
        # 4GB memory limit
        resource.setrlimit(resource.RLIMIT_AS, (4 * 1024 * 1024 * 1024, -1))
        # 5 minute CPU time limit
        resource.setrlimit(resource.RLIMIT_CPU, (300, -1))
    except Exception as e:
        logger.error(f"Failed to set resource limits: {e}")


def run_analyzer_directly(pdf_path, page_num, output_path, dpi=200, timeout=120):
    """Run the analyzer directly with robust process management and fallbacks."""
    logger.info(f"Running analyzer directly for page {page_num} with timeout {timeout}s")

    # Create the output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Prepare the analyzer command
    analyzer_cmd = [
        sys.executable,  # Use current Python interpreter
        "analyzer.py",
        "--image", pdf_path,
        "--page", str(page_num),
        "--output", output_path,
        "--dpi", str(dpi)
    ]

    try:
        # Start the analyzer process
        process = subprocess.Popen(
            analyzer_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        logger.info(f"Started analyzer process with PID {process.pid}")

        # Set up process monitoring
        start_time = time.time()
        timed_out = False
        stdout_data = []
        stderr_data = []

        # Monitor the process
        while process.poll() is None:
            # Check for timeout
            if time.time() - start_time > timeout:
                logger.warning(f"Analyzer process timed out after {timeout}s")
                timed_out = True

                # Kill the process
                try:
                    logger.info(f"Killing analyzer process {process.pid}")
                    process.kill()
                except Exception as e:
                    logger.error(f"Error killing process: {e}")

                # Kill any child processes (platform-specific)
                try:
                    if sys.platform != 'win32':
                        # UNIX-like: Find and kill all python processes related to this analyzer
                        if shutil.which('pkill'):
                            os.system(f"pkill -9 -f 'analyzer.py.*{page_num}'")
                        else:
                            # Basic process kill using POSIX tools
                            os.system(f"kill -9 {process.pid}")
                    else:
                        # Windows: Use taskkill to kill process tree
                        os.system(f"taskkill /F /T /PID {process.pid}")
                except Exception as e:
                    logger.error(f"Error killing child processes: {e}")

                break

            # Read output without blocking
            readable = []
            try:
                readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)
            except (ImportError, OSError, select.error):
                # Fallback for systems without select
                time.sleep(0.1)

            for stream in readable:
                line = stream.readline()
                if line:
                    if stream == process.stdout:
                        stdout_data.append(line)
                        logger.debug(f"Analyzer stdout: {line.strip()}")
                    else:
                        stderr_data.append(line)
                        logger.debug(f"Analyzer stderr: {line.strip()}")

            # Sleep to avoid CPU spin
            time.sleep(0.1)

        # Get the return code
        return_code = process.poll()

        # Read any remaining output
        try:
            out, err = process.communicate(timeout=1)
            logger.info(f"Visualizer stdout: {stdout}")
            logger.error(f"Visualizer stderr: {stderr}")
            if out:
                stdout_data.append(out)
            if err:
                stderr_data.append(err)
        except:
            pass

        # Combine the outputs
        stdout = "".join(stdout_data)
        stderr = "".join(stderr_data)

        # Check for success
        success = (return_code == 0) and not timed_out

        # Create fallback if needed
        if not success or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            logger.warning(f"Creating fallback doctags file for page {page_num}")
            with open(output_path, "w") as f:
                if timed_out:
                    f.write(f"<doctag><text>Analyzer timed out after {timeout} seconds</text></doctag>")
                elif return_code != 0:
                    f.write(f"<doctag><text>Analyzer failed with exit code {return_code}</text></doctag>")
                else:
                    f.write("<doctag><text>Analyzer completed but no output was produced</text></doctag>")

        logger.info(f"Analyzer finished for page {page_num}, success={success}, return_code={return_code}")
        return success, stdout, stderr

    except Exception as e:
        logger.error(f"Exception running analyzer: {str(e)}", exc_info=True)

        # Create fallback output
        with open(output_path, "w") as f:
            f.write(f"<doctag><text>Error running analyzer: {str(e)}</text></doctag>")

        return False, "", str(e)


def run_fix_scaling_directly(doctags_path, output_path, x_factor=0.7, y_factor=0.7, timeout=30):
    """Run the fix_scaling script directly with robust process management and fallbacks."""
    logger.info(f"Running fix_scaling directly with timeout {timeout}s")

    # Create the output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Prepare the fix_scaling command
    fix_scaling_cmd = [
        sys.executable,  # Use current Python interpreter
        "fix_scaling.py",
        "--doctags", doctags_path,
        "--output", output_path,
        "--x-factor", str(x_factor),
        "--y-factor", str(y_factor)
    ]

    try:
        # Start the fix_scaling process
        process = subprocess.Popen(
            fix_scaling_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        logger.info(f"Started fix_scaling process with PID {process.pid}")

        # Set up process monitoring
        start_time = time.time()
        timed_out = False
        stdout_data = []
        stderr_data = []

        # Monitor the process
        while process.poll() is None:
            # Check for timeout
            if time.time() - start_time > timeout:
                logger.warning(f"Fix_scaling process timed out after {timeout}s")
                timed_out = True

                # Kill the process
                try:
                    logger.info(f"Killing fix_scaling process {process.pid}")
                    process.kill()
                except Exception as e:
                    logger.error(f"Error killing process: {e}")

                # Kill any child processes (platform-specific)
                try:
                    if sys.platform != 'win32':
                        # UNIX-like: Find and kill all python processes related to this fix_scaling
                        if shutil.which('pkill'):
                            os.system(f"pkill -9 -f 'fix_scaling.py.*{doctags_path}'")
                        else:
                            # Basic process kill using POSIX tools
                            os.system(f"kill -9 {process.pid}")
                    else:
                        # Windows: Use taskkill to kill process tree
                        os.system(f"taskkill /F /T /PID {process.pid}")
                except Exception as e:
                    logger.error(f"Error killing child processes: {e}")

                break

            # Read output without blocking
            readable = []
            try:
                readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)
            except (ImportError, OSError, select.error):
                # Fallback for systems without select
                time.sleep(0.1)

            for stream in readable:
                line = stream.readline()
                if line:
                    if stream == process.stdout:
                        stdout_data.append(line)
                    else:
                        stderr_data.append(line)

            # Sleep to avoid CPU spin
            time.sleep(0.1)

        # Get the return code
        return_code = process.poll()

        # Read any remaining output
        try:
            out, err = process.communicate(timeout=1)
            if out:
                stdout_data.append(out)
            if err:
                stderr_data.append(err)
        except:
            pass

        # Combine the outputs
        stdout = "".join(stdout_data)
        stderr = "".join(stderr_data)

        # Check for success
        success = (return_code == 0) and not timed_out

        if not success or not os.path.exists(output_path):
            logger.warning(f"Fix_scaling failed or timed out, copying original file as fallback")
            shutil.copy2(doctags_path, output_path)

        logger.info(f"Fix_scaling finished, success={success}, return_code={return_code}")
        return success, stdout, stderr

    except Exception as e:
        logger.error(f"Exception running fix_scaling: {str(e)}", exc_info=True)

        # Use original as fallback
        shutil.copy2(doctags_path, output_path)

        return False, "", str(e)


def run_with_timeout(cmd, timeout=60):
    """Run a command with timeout, forcibly terminating it if it exceeds the timeout."""
    process = None
    start_time = time.time()

    logger.info(f"Starting command: {' '.join(cmd)}")

    try:
        # Start the process
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            preexec_fn=set_process_limits if hasattr(os, 'setsid') else None
        )

        # Set up non-blocking reads using select
        readable = {process.stdout: [], process.stderr: []}
        timeout_check_interval = 0.5  # Check for timeout every 0.5 seconds
        last_timeout_check = time.time()

        # Continue while process is alive
        while process.poll() is None:
            # Use select with a short timeout to enable non-blocking reads
            ready, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)

            for stream in ready:
                line = stream.readline()
                if line:
                    readable[stream].append(line)

            # Periodically check if we've exceeded timeout
            current_time = time.time()
            if current_time - last_timeout_check >= timeout_check_interval:
                last_timeout_check = current_time

                if current_time - start_time > timeout:
                    logger.warning(f"Command timed out after {timeout} seconds: {' '.join(cmd)}")

                    # First attempt: Try SIGTERM on process group
                    try:
                        if hasattr(os, 'killpg'):
                            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                        else:
                            process.terminate()

                        # Give it a moment to terminate gracefully
                        termination_wait = 0.5
                        termination_deadline = time.time() + termination_wait
                        while time.time() < termination_deadline and process.poll() is None:
                            time.sleep(0.1)
                    except Exception as e:
                        logger.error(f"Error during graceful termination: {e}")

                    # If still running, force kill
                    if process.poll() is None:
                        try:
                            logger.warning("Process still running after SIGTERM, using SIGKILL")
                            if hasattr(os, 'killpg'):
                                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                            else:
                                process.kill()

                            # Give it a moment to be killed
                            time.sleep(0.5)
                        except Exception as e:
                            logger.error(f"Error during force kill: {e}")

                    # Last resort: Use external kill command on Unix-like systems
                    if process.poll() is None and not sys.platform.startswith('win'):
                        try:
                            logger.warning("Process still running after SIGKILL, using external kill command")
                            if shutil.which('pkill'):
                                os.system(f"pkill -9 -f '{cmd[0]}'")
                            else:
                                os.system(f"kill -9 {process.pid}")
                        except Exception as e:
                            logger.error(f"Error during external kill: {e}")

                    # Collect any final output
                    try:
                        # Set a very short timeout for any remaining reads
                        ready, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)
                        for stream in ready:
                            line = stream.readline()
                            if line:
                                readable[stream].append(line)
                    except:
                        pass

                    return None, "Process timed out and was terminated", "".join(readable[process.stderr]), True

            # Avoid CPU spin
            time.sleep(0.01)

        # Process has completed, read any remaining output
        while True:
            ready, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)
            if not ready:
                break

            for stream in ready:
                line = stream.readline()
                if not line:  # Stream closed with no more data
                    continue
                readable[stream].append(line)

        stdout = "".join(readable[process.stdout])
        stderr = "".join(readable[process.stderr])

        logger.info(f"Command completed with return code {process.returncode}")

        return process.returncode, stdout, stderr, False

    except Exception as e:
        logger.error(f"Error running command: {e}", exc_info=True)

        # Make sure to kill the process if it's still running
        if process and process.poll() is None:
            try:
                if hasattr(os, 'killpg'):
                    os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                else:
                    process.kill()
            except:
                pass

        return None, f"Exception: {str(e)}", "", True


def process_page(job_id, pdf_path, page_num, x_factor=0.7, y_factor=0.7, dpi=200):
    """Process a single page using direct script calls with robust process control"""
    try:
        # Track start time for the whole page processing
        page_start_time = time.time()

        # Update job status
        jobs[job_id]['status'] = 'running'
        jobs[job_id]['progress'] = 10
        jobs[job_id]['current_page'] = page_num
        jobs[job_id]['current_step'] = 'Starting page processing'

        # Create output directory
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        os.makedirs(result_dir, exist_ok=True)

        # Define output file paths
        doctags_path = os.path.join(result_dir, f"page_{page_num}.doctags.txt")
        fixed_doctags_path = os.path.join(result_dir, f"page_{page_num}.fixed.doctags.txt")
        html_path = os.path.join(result_dir, f"page_{page_num}.html")
        debug_img_path = os.path.join(result_dir, f"page_{page_num}.debug.png")

        # Check if we've been processing too long already
        if time.time() - page_start_time > MAX_PAGE_PROCESSING_TIME:
            logger.warning(f"Page {page_num} processing time limit exceeded, creating fallbacks")
            create_fallback_files(doctags_path, fixed_doctags_path, html_path, debug_img_path, page_num)
            jobs[job_id]['completed_pages'].append(page_num)
            jobs[job_id]['errors'].append(f"Page {page_num}: Processing time limit exceeded")
            return True

        # Step 1: Run analyzer
        jobs[job_id]['progress'] = 30
        jobs[job_id]['current_step'] = 'Running analyzer'

        # Run analyzer directly with retry mechanism
        max_attempts = 2  # Try up to 2 times
        analyzer_success = False

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Running analyzer on {pdf_path}, page {page_num} (attempt {attempt}/{max_attempts})")

            # Use a shorter timeout for the second attempt
            timeout = 120 if attempt == 1 else 60

            # Run the analyzer directly
            success, stdout, stderr = run_analyzer_directly(
                pdf_path,
                page_num,
                doctags_path,
                dpi=dpi,
                timeout=timeout
            )

            if success:
                analyzer_success = True
                break

            if attempt < max_attempts:
                logger.info(f"Retrying analyzer (attempt {attempt}/{max_attempts} failed)")
                # Sleep briefly before retry to allow system to recover
                time.sleep(2)
            else:
                logger.error(f"All analyzer attempts failed for page {page_num}")
                jobs[job_id]['errors'].append(f"Page {page_num}: Analyzer failed after {max_attempts} attempts")

        # Check if doctags file exists
        if not os.path.exists(doctags_path) or os.path.getsize(doctags_path) == 0:
            logger.warning(f"Doctags file not found or empty at expected path: {doctags_path}")
            with open(doctags_path, 'w') as f:
                f.write("<doctag><text>Fallback DocTags content</text></doctag>")

        # Check if we've been processing too long already
        if time.time() - page_start_time > MAX_PAGE_PROCESSING_TIME:
            logger.warning(f"Page {page_num} processing time limit exceeded after analyzer, creating fallbacks")
            create_fallback_files(doctags_path, fixed_doctags_path, html_path, debug_img_path, page_num)
            jobs[job_id]['completed_pages'].append(page_num)
            jobs[job_id]['errors'].append(f"Page {page_num}: Processing time limit exceeded after analyzer")
            return True

        # Step 2: Fix scaling
        jobs[job_id]['progress'] = 60
        jobs[job_id]['current_step'] = 'Fixing scaling'

        # Run fix_scaling directly with a timeout
        logger.info(f"Running fix_scaling on {doctags_path}")
        success, stdout, stderr = run_fix_scaling_directly(
            doctags_path,
            fixed_doctags_path,
            x_factor=x_factor,
            y_factor=y_factor,
            timeout=30  # Use a shorter timeout for fix_scaling
        )

        # Check if fixed doctags file exists
        if not os.path.exists(fixed_doctags_path):
            logger.warning(f"Fixed doctags file not found at expected path: {fixed_doctags_path}")
            # Use original file as fallback
            shutil.copy2(doctags_path, fixed_doctags_path)

        # Check if we've been processing too long already
        if time.time() - page_start_time > MAX_PAGE_PROCESSING_TIME:
            logger.warning(f"Page {page_num} processing time limit exceeded after fix_scaling, creating fallbacks")
            create_fallback_files(doctags_path, fixed_doctags_path, html_path, debug_img_path, page_num)
            jobs[job_id]['completed_pages'].append(page_num)
            jobs[job_id]['errors'].append(f"Page {page_num}: Processing time limit exceeded after fix_scaling")
            return True

        # Step 3: Visualize
        jobs[job_id]['progress'] = 80
        jobs[job_id]['current_step'] = 'Creating visualization'

        # Run visualizer directly
        logger.info(f"Running visualizer on {fixed_doctags_path}, page {page_num}")
        success, stdout, stderr = run_visualizer_directly(
            fixed_doctags_path,
            pdf_path,
            page_num,
            html_path,
            timeout=60
        )

        # Debug image path from the visualization
        debug_img_path = html_path.replace('.html', '.debug.png')

        # Check if output files exist
        if not os.path.exists(html_path):
            logger.warning(f"HTML file not found at expected path: {html_path}")
            create_fallback_html(html_path, page_num)

        if not os.path.exists(debug_img_path):
            logger.warning(f"Debug image not found at expected path: {debug_img_path}")
            create_fallback_image(debug_img_path, page_num)

        # Add page to successful pages
        jobs[job_id]['completed_pages'].append(page_num)
        jobs[job_id]['progress'] = 100
        jobs[job_id]['current_step'] = 'Page processing complete'

        return True

    except Exception as e:
        logger.error(f"Error processing page {page_num}: {str(e)}", exc_info=True)
        jobs[job_id]['errors'].append(f"Page {page_num}: Unexpected error: {str(e)}")

        # Create fallback files to ensure the page is marked as completed
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        doctags_path = os.path.join(result_dir, f"page_{page_num}.doctags.txt")
        fixed_doctags_path = os.path.join(result_dir, f"page_{page_num}.fixed.doctags.txt")
        html_path = os.path.join(result_dir, f"page_{page_num}.html")
        debug_img_path = os.path.join(result_dir, f"page_{page_num}.debug.png")

        create_fallback_files(doctags_path, fixed_doctags_path, html_path, debug_img_path, page_num)

        # Still add the page to completed pages since we created fallbacks
        jobs[job_id]['completed_pages'].append(page_num)

        return True


def kill_hung_processes():
    """Find and kill any analyzer.py processes that have been running too long.
    Ultra-simplified version that works on macOS/BSD systems.
    """
    try:
        # Check if we have pkill (available on macOS with homebrew or most Linux distros)
        if shutil.which('pkill'):
            try:
                # The -f option searches the entire command line
                os.system("pkill -9 -f analyzer.py")
                os.system("pkill -9 -f fix_scaling.py")
                logger.info("Used pkill to clean up processes")
                return
            except Exception as e:
                logger.error(f"Error using pkill: {e}")

        # Fall back to ps/grep with compatible format for BSD/macOS
        try:
            # This simple format works on macOS/BSD
            os.system("ps -ax | grep python | grep -v grep | awk '{print $1}' | xargs kill -9 2>/dev/null || true")
            logger.info("Used BSD-compatible ps to clean up processes")
        except Exception as e:
            logger.error(f"Error using basic process cleanup: {e}")
    except Exception as e:
        logger.error(f"Error in kill_hung_processes: {e}")

def run_visualizer_directly(doctags_path, pdf_path, page_num, output_path, timeout=60):
    """Run the visualizer directly with robust process management and fallbacks."""
    logger.info(f"Running visualizer directly for page {page_num} with timeout {timeout}s")

    # Create the output directory
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # Prepare the visualizer command
    visualizer_cmd = [
        sys.executable,  # Use current Python interpreter
        "visualizer.py",
        "--doctags", doctags_path,
        "--pdf", pdf_path,
        "--page", str(page_num),
        "--output", output_path,
        "--adjust"
    ]

    try:
        # Start the visualizer process
        process = subprocess.Popen(
            visualizer_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        logger.info(f"Started visualizer process with PID {process.pid}")

        # Set up process monitoring
        start_time = time.time()
        timed_out = False
        stdout_data = []
        stderr_data = []

        # Monitor the process
        while process.poll() is None:
            # Check for timeout
            if time.time() - start_time > timeout:
                logger.warning(f"Visualizer process timed out after {timeout}s")
                timed_out = True

                # Kill the process
                try:
                    logger.info(f"Killing visualizer process {process.pid}")
                    process.kill()
                except Exception as e:
                    logger.error(f"Error killing process: {e}")

                # Kill any child processes
                try:
                    if sys.platform != 'win32':
                        if shutil.which('pkill'):
                            os.system(f"pkill -9 -f 'visualizer.py.*{page_num}'")
                        else:
                            os.system(f"kill -9 {process.pid}")
                    else:
                        os.system(f"taskkill /F /T /PID {process.pid}")
                except Exception as e:
                    logger.error(f"Error killing child processes: {e}")

                break

            # Read output without blocking
            readable = []
            try:
                readable, _, _ = select.select([process.stdout, process.stderr], [], [], 0.1)
            except Exception:
                # Fallback for systems without select
                time.sleep(0.1)

            for stream in readable:
                line = stream.readline()
                if line:
                    if stream == process.stdout:
                        stdout_data.append(line)
                    else:
                        stderr_data.append(line)

            # Sleep to avoid CPU spin
            time.sleep(0.1)

        # Get the return code
        return_code = process.poll()

        # Read any remaining output
        try:
            out, err = process.communicate(timeout=1)
            if out:
                stdout_data.append(out)
            if err:
                stderr_data.append(err)
        except:
            pass

        # Combine the outputs
        stdout = "".join(stdout_data)
        stderr = "".join(stderr_data)

        # Check for success
        success = (return_code == 0) and not timed_out

        # Create fallback if needed
        if not success or not os.path.exists(output_path):
            logger.warning(f"Visualizer failed or timed out, creating fallback visualization")
            create_fallback_html(output_path, page_num)

            # Also create a fallback debug image
            debug_img_path = output_path.replace('.html', '.debug.png')
            if not os.path.exists(debug_img_path):
                create_fallback_image(debug_img_path, page_num)

        logger.info(f"Visualizer finished for page {page_num}, success={success}, return_code={return_code}")
        return success, stdout, stderr

    except Exception as e:
        logger.error(f"Exception running visualizer: {str(e)}", exc_info=True)

        # Create fallback HTML
        create_fallback_html(output_path, page_num)

        # Also create a fallback debug image
        debug_img_path = output_path.replace('.html', '.debug.png')
        create_fallback_image(debug_img_path, page_num)

        return False, "", str(e)

def create_fallback_files(doctags_path, fixed_doctags_path, html_path, debug_img_path, page_num):
    """Create all necessary fallback files for a page"""
    try:
        # Create fallback doctags file if it doesn't exist
        if not os.path.exists(doctags_path):
            with open(doctags_path, 'w') as f:
                f.write("<doctag><text>Error processing page</text></doctag>")

        # Create fallback fixed doctags file if it doesn't exist
        if not os.path.exists(fixed_doctags_path):
            if os.path.exists(doctags_path):
                shutil.copy2(doctags_path, fixed_doctags_path)
            else:
                with open(fixed_doctags_path, 'w') as f:
                    f.write("<doctag><text>Error processing page</text></doctag>")

        # Create fallback HTML file if it doesn't exist
        if not os.path.exists(html_path):
            create_fallback_html(html_path, page_num)

        # Create fallback debug image if it doesn't exist
        if not os.path.exists(debug_img_path):
            create_fallback_image(debug_img_path, page_num)

    except Exception as e:
        logger.error(f"Error creating fallback files: {str(e)}", exc_info=True)


def create_fallback_html(output_path, page_num):
    """Create a nicer fallback HTML file"""
    try:
        with open(output_path, 'w') as f:
            f.write(f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>DocTags Visualization - Page {page_num}</title>
    <style>
        body {{ 
            font-family: Arial, sans-serif; 
            margin: 0;
            padding: 0;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 800px;
            margin: 40px auto;
            padding: 20px;
            background-color: white;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border-radius: 5px;
        }}
        h1 {{ 
            color: #2962ff;
            border-bottom: 1px solid #eee;
            padding-bottom: 10px;
        }}
        .placeholder {{ 
            border: 2px dashed #ddd; 
            padding: 40px; 
            text-align: center;
            border-radius: 8px;
            background-color: #f9f9f9;
            margin: 20px 0;
        }}
        pre {{
            background-color: #f0f0f0;
            padding: 10px;
            border-radius: 4px;
            overflow-x: auto;
        }}
        .footer {{
            margin-top: 40px;
            color: #666;
            font-size: 12px;
            text-align: center;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>DocTags Visualization - Page {page_num}</h1>
        
        <div class="placeholder">
            <h2>Document Content</h2>
            <p>This page couldn't be processed with full visualization.</p>
            <p>A simplified representation is available.</p>
        </div>
        
        <h3>Document Tags</h3>
        <pre>&lt;doctag&gt;
  &lt;text&gt;Document content would appear here&lt;/text&gt;
&lt;/doctag&gt;</pre>
        
        <div class="footer">
            DocTags Processing System
        </div>
    </div>
</body>
</html>""")
    except Exception as e:
        logger.error(f"Error creating fallback HTML: {str(e)}")
        # Absolute fallback - create empty file
        try:
            with open(output_path, 'w') as f:
                f.write("<html><body>Error creating fallback HTML</body></html>")
        except:
            pass


def create_fallback_image(output_path, page_num):
    """Create a higher quality fallback debug image"""
    try:
        # Create a better quality fallback image
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new('RGB', (800, 600), color=(250, 250, 250))
        draw = ImageDraw.Draw(img)

        # Add border
        draw.rectangle([(10, 10), (790, 590)], outline=(100, 100, 100), width=2)

        # Add gradient background
        for y in range(50, 550):
            color = int(200 + (y - 50) * 0.1)
            draw.line([(50, y), (750, y)], fill=(color, color, color), width=1)

        # Add page info
        draw.text((400, 100), f"Page {page_num}", fill=(50, 50, 50), anchor="mm")
        draw.text((400, 250), "Preview Unavailable", fill=(80, 80, 80), anchor="mm")
        draw.text((400, 400), "Fallback Image", fill=(100, 100, 100), anchor="mm")

        img.save(output_path)
    except Exception as e:
        logger.error(f"Error creating fallback image: {str(e)}")
        # Create a basic empty file as absolute fallback
        try:
            with open(output_path, 'wb') as f:
                f.write(b'')
        except:
            pass


def process_document(job_id, pdf_path, pages, x_factor=0.7, y_factor=0.7, dpi=200):
    """Process a document (all or selected pages) with improved progress tracking and error handling."""
    try:
        total_pages = len(pages)
        jobs[job_id]['total_pages'] = total_pages
        jobs[job_id]['status'] = 'running'

        for i, page_num in enumerate(pages):
            # Update job progress
            overall_progress = int((i / total_pages) * 100)
            jobs[job_id]['progress'] = overall_progress
            logger.info(f"Processing page {page_num} ({i+1} of {total_pages}) for job {job_id}")

            # Process the page
            process_page(job_id, pdf_path, page_num, x_factor, y_factor, dpi)

        # Create index.html to navigate between pages
        create_index_html(job_id)

        # Complete the job
        jobs[job_id]['status'] = 'completed'
        jobs[job_id]['progress'] = 100
        jobs[job_id]['current_step'] = 'Done'
        jobs[job_id]['end_time'] = time.time()

        # Calculate success rate
        success_rate = (len(jobs[job_id]['completed_pages']) / total_pages) * 100 if total_pages > 0 else 0
        jobs[job_id]['success_rate'] = success_rate

        logger.info(f"Job {job_id} completed with {success_rate:.1f}% success rate")

    except Exception as e:
        logger.error(f"Error processing document: {str(e)}", exc_info=True)
        jobs[job_id]['status'] = 'error'
        jobs[job_id]['errors'].append(str(e))

    finally:
        # Make sure job status is not stuck as 'running'
        if jobs[job_id]['status'] == 'running':
            jobs[job_id]['status'] = 'completed'

        # Store job results
        save_job_results(job_id)


def create_index_html(job_id):
    """Create an index.html file to navigate between pages with correct file URLs."""
    try:
        result_dir = os.path.join(RESULTS_FOLDER, job_id)
        job_info = jobs[job_id]
        pdf_name = os.path.basename(job_info['pdf_path'])

        index_path = os.path.join(result_dir, "index.html")

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

        # Add cards for each completed page with CORRECT URLs - using /api/results/{job_id}/files/{filename}
        for page_num in sorted(job_info['completed_pages']):
            debug_img = f"page_{page_num}.debug.png"
            html_file = f"page_{page_num}.html"

            debug_path = os.path.join(result_dir, debug_img)
            if os.path.exists(debug_path):
                html += f"""
            <div class="card">
                <a href="/api/results/{job_id}/files/{html_file}" target="_blank">
                    <img src="/api/results/{job_id}/files/{debug_img}" alt="Page {page_num}">
                    <div class="card-content">
                        <h3 class="card-title">Page {page_num}</h3>
                    </div>
                </a>
            </div>
"""
            else:
                # No debug image available, use text placeholder
                html += f"""
            <div class="card">
                <a href="/api/results/{job_id}/files/{html_file}" target="_blank">
                    <div style="height: 200px; display: flex; align-items: center; justify-content: center; background-color: #eee;">
                        <span style="font-size: 24px; color: #666;">Page {page_num}</span>
                    </div>
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

        # Also create a copy named old.html for compatibility
        old_html_path = os.path.join(result_dir, "old.html")
        with open(old_html_path, 'w', encoding='utf-8') as f:
            f.write(html)

        logger.info(f"Created index.html for job {job_id}")

    except Exception as e:
        logger.error(f"Error creating index.html: {str(e)}", exc_info=True)


def count_pdf_pages(pdf_path):
    """Count the number of pages in a PDF file with multiple fallback methods."""
    logger.info(f"Counting pages in {pdf_path}")

    # Method 1: Try using PyPDF2 if available
    try:
        import PyPDF2
        with open(pdf_path, 'rb') as file:
            try:
                # Try the newer PdfReader first
                pdf_reader = PyPDF2.PdfReader(file)
                page_count = len(pdf_reader.pages)
            except (AttributeError, NameError):
                # Fall back to the older PdfFileReader
                file.seek(0)
                pdf_reader = PyPDF2.PdfFileReader(file)
                page_count = pdf_reader.getNumPages()

            logger.info(f"PDF has {page_count} pages (using PyPDF2)")
            return page_count
    except ImportError:
        logger.warning("PyPDF2 not available, trying other methods")
    except Exception as e:
        logger.error(f"Error counting pages with PyPDF2: {str(e)}")

    # Method 2: Try using pdf2image directly
    try:
        from pdf2image.pdf2image import pdfinfo_from_path
        info = pdfinfo_from_path(pdf_path, userpw=None, poppler_path=None)
        page_count = info["Pages"]
        logger.info(f"PDF has {page_count} pages (using pdf2image)")
        return page_count
    except Exception as e:
        logger.error(f"Error counting pages with pdf2image: {str(e)}")

    # Method 3: Try using the visualizer
    try:
        cmd = [
            sys.executable,  # Use current Python interpreter
            "visualizer.py",
            "--pdf", pdf_path,
            "--page-count"
        ]

        return_code, stdout, stderr, timed_out = run_with_timeout(cmd, timeout=30)

        if not timed_out and stdout:
            for line in stdout.split('\n'):
                if "The PDF has" in line:
                    page_count = int(line.split("The PDF has")[1].split("pages")[0].strip())
                    logger.info(f"PDF has {page_count} pages (using visualizer)")
                    return page_count
    except Exception as e:
        logger.error(f"Error counting pages with visualizer: {str(e)}")

    # Method 4: Fallback to assuming 1 page
    logger.warning("All page counting methods failed, assuming PDF has 1 page")
    return 1


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
        logger.error(f"Error saving job results: {str(e)}", exc_info=True)


def start_watchdog():
    """Start a watchdog thread to monitor jobs and terminate any that have been running too long"""
    def watchdog_thread():
        while True:
            try:
                current_time = time.time()

                # Check each running job
                for job_id, job in list(jobs.items()):
                    if job.get('status') == 'running':
                        # Calculate how long the job has been running
                        start_time = job.get('start_time', current_time)
                        running_time = current_time - start_time

                        # If a job has been running for more than 30 minutes, something is wrong
                        if running_time > 1800:  # 30 minutes
                            logger.warning(f"Watchdog: Job {job_id} has been running for {running_time:.1f} seconds, forcing completion")

                            # Force the job to complete
                            job['status'] = 'completed'
                            job['progress'] = 100
                            job['current_step'] = 'Force completed by watchdog'
                            job['end_time'] = current_time
                            job['errors'].append("Job was force-completed by watchdog after running too long")

                            # Calculate success rate
                            if job.get('total_pages', 0) > 0:
                                success_rate = (len(job.get('completed_pages', [])) / job['total_pages']) * 100
                            else:
                                success_rate = 0
                            job['success_rate'] = success_rate

                            # Create index.html
                            try:
                                create_index_html(job_id)
                            except Exception as e:
                                logger.error(f"Error creating index for force-completed job: {e}")

                            # Save job results
                            save_job_results(job_id)

                # Look for and kill any hung analyzer processes
                kill_hung_processes()

            except Exception as e:
                logger.error(f"Error in watchdog thread: {e}", exc_info=True)

            # Sleep for 60 seconds before checking again
            time.sleep(60)

    # Start the watchdog thread
    watchdog = threading.Thread(target=watchdog_thread)
    watchdog.daemon = True
    watchdog.start()
    logger.info("Watchdog thread started")


# API Endpoints

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({'status': 'ok'})


@app.route('/api/upload', methods=['POST'])
def upload_pdf():
    """Upload a PDF file with improved error handling and filename sanitization."""
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

        # Sanitize filename to avoid issues with special characters
        sanitized_filename = secure_filename(file.filename)
        if not sanitized_filename:
            sanitized_filename = f"uploaded_document_{job_id}.pdf"

        # Save the file
        file_path = os.path.join(upload_dir, sanitized_filename)
        file.save(file_path)

        logger.info(f"Saved uploaded file to {file_path}")

        # Verify file was saved correctly
        if not os.path.exists(file_path):
            return jsonify({'error': 'Failed to save uploaded file'}), 500

        if os.path.getsize(file_path) == 0:
            return jsonify({'error': 'Uploaded file is empty'}), 400

        # Count pages with improved error handling
        page_count = count_pdf_pages(file_path)

        if page_count == 0:
            logger.error(f"Could not determine page count for {file_path}")
            return jsonify({
                'error': 'Could not determine page count or PDF has no pages. The file may be corrupted or password-protected.',
                'job_id': job_id,
                'file_name': sanitized_filename
            }), 400

        # Create job entry
        jobs[job_id] = {
            'id': job_id,
            'pdf_path': file_path,
            'file_name': sanitized_filename,
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

        logger.info(f"PDF uploaded: {sanitized_filename}, job ID: {job_id}, pages: {page_count}")

        return jsonify({
            'job_id': job_id,
            'file_name': sanitized_filename,
            'page_count': page_count,
            'status': 'uploaded'
        })

    except Exception as e:
        logger.error(f"Error uploading file: {str(e)}", exc_info=True)
        return jsonify({'error': f"Upload failed: {str(e)}"}), 500


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
        logger.error(f"Error processing PDF: {str(e)}", exc_info=True)
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


@app.route('/api/jobs/<job_id>/force-complete', methods=['POST'])
def force_complete_job(job_id):
    """Force-complete a job that appears to be stuck."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    job = jobs[job_id]

    # Only apply to running jobs
    if job['status'] != 'running':
        return jsonify({'error': 'Job is not running, cannot force-complete'}), 400

    logger.warning(f"Force-completing job {job_id} at user request")

    # Force job to complete state
    job['status'] = 'completed'
    job['progress'] = 100
    job['current_step'] = 'Force completed by user'
    job['end_time'] = time.time()
    job['errors'].append("Job was force-completed at user request")

    # Calculate success rate
    if job.get('total_pages', 0) > 0:
        success_rate = (len(job.get('completed_pages', [])) / job['total_pages']) * 100
    else:
        success_rate = 0
    job['success_rate'] = success_rate

    # Create index.html
    try:
        create_index_html(job_id)
    except Exception as e:
        logger.error(f"Error creating index for force-completed job: {e}")

    # Save job results
    save_job_results(job_id)

    # Kill any running processes for this job
    if sys.platform != 'win32':
        try:
            if shutil.which('pkill'):
                os.system(f"pkill -9 -f '{job_id}'")
            else:
                # Basic process kill using more portable syntax
                os.system(f"ps -ef | grep {job_id} | grep -v grep | awk '{{print $2}}' | xargs -r kill -9")
        except Exception as e:
            logger.error(f"Error killing processes for job {job_id}: {e}")

    return jsonify({
        'job_id': job_id,
        'status': 'completed',
        'message': 'Job force-completed successfully'
    })


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


@app.route('/api/results/<job_id>/files/<path:filename>', methods=['GET'])
def get_result_file(job_id, filename):
    """Get a specific result file with support for path-like filenames."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    # Sanitize the filename to prevent directory traversal attacks
    safe_filename = os.path.normpath(filename).lstrip('/')
    file_path = os.path.join(RESULTS_FOLDER, job_id, safe_filename)

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        logger.warning(f"File not found: {file_path}")
        return jsonify({'error': 'File not found'}), 404

    return send_file(file_path)


# Support direct access to files without the /files/ path segment
@app.route('/api/results/<job_id>/<path:filename>', methods=['GET'])
def get_result_file_direct(job_id, filename):
    """Direct access to result files for backward compatibility."""
    # Redirect to the proper endpoint
    return get_result_file(job_id, filename)


@app.route('/api/results/<job_id>/view', methods=['GET'])
def view_results(job_id):
    """Redirect to the index.html file for viewing results."""
    if job_id not in jobs:
        return jsonify({'error': 'Job not found'}), 404

    # Try to use index.html first
    index_path = os.path.join(RESULTS_FOLDER, job_id, "index.html")
    if os.path.exists(index_path):
        return send_file(index_path)

    # Fall back to old.html if index.html doesn't exist
    old_html_path = os.path.join(RESULTS_FOLDER, job_id, "old.html")
    if os.path.exists(old_html_path):
        return send_file(old_html_path)

    return jsonify({'error': 'Results not found'}), 404


@app.route('/api/params', methods=['GET'])
def get_default_params():
    """Get default parameters."""
    return jsonify({
        'x_factor': 0.7,
        'y_factor': 0.7,
        'dpi': 200
    })


@app.route('/api/fix-paths', methods=['GET'])
def fix_paths():
    """Fix path inconsistencies in the results folders."""
    try:
        fixed_count = 0

        # Get all result directories
        for job_dir in os.listdir(RESULTS_FOLDER):
            job_path = os.path.join(RESULTS_FOLDER, job_dir)
            if not os.path.isdir(job_path):
                continue

            # Look for doctags files with inconsistent extensions
            for filename in os.listdir(job_path):
                if '.doctags.doctags.' in filename:
                    # Fix double extension
                    old_path = os.path.join(job_path, filename)
                    new_path = os.path.join(job_path, filename.replace('.doctags.doctags.', '.doctags.'))

                    if not os.path.exists(new_path):
                        shutil.copy2(old_path, new_path)
                        logger.info(f"Fixed path: {old_path} -> {new_path}")
                        fixed_count += 1

        return jsonify({
            'success': True,
            'message': f'Fixed {fixed_count} path inconsistencies'
        })

    except Exception as e:
        logger.error(f"Error fixing paths: {str(e)}", exc_info=True)
        return jsonify({'error': str(e)}), 500


@app.route('/', methods=['GET'])
def serve_frontend():
    """Serve the frontend HTML."""
    # Check if index.html exists
    frontend_path = "index.html"
    if os.path.exists(frontend_path):
        return send_file(frontend_path)
    else:
        return jsonify({'error': 'Frontend not found. Please place index.html in the root directory.'}), 404


# Start the watchdog thread
start_watchdog()

if __name__ == '__main__':
    print("DocTags API starting on http://localhost:5000")
    print("Use the following endpoints:")
    print("  - POST /api/upload: Upload a PDF file")
    print("  - POST /api/process: Process a PDF file")
    print("  - GET /api/jobs/<job_id>: Get job status")
    print("  - GET /api/results/<job_id>: Get job results")
    print("  - GET /api/results/<job_id>/view: View job results")
    print("  - GET /api/fix-paths: Fix path inconsistencies")
    print("")
    print("Frontend will be served at http://localhost:5000/ if index.html exists")

    app.run(debug=True, host='0.0.0.0')