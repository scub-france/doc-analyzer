#!/usr/bin/env python3
"""
Batch Processor for DocTags
Handles batch processing of PDF documents with parallel processing support
"""

import os
import json
import time
import threading
import queue
import logging
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import shutil
import zipfile

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchProcessor:
    def __init__(self, batch_id, pdf_file, start_page, end_page, options):
        self.batch_id = batch_id
        self.pdf_file = pdf_file
        self.start_page = start_page
        self.end_page = end_page
        self.total_pages = end_page - start_page + 1
        self.options = options

        # State management
        self.state = {
            'status': 'initializing',
            'processed': 0,
            'total': self.total_pages,
            'start_time': time.time(),
            'completed': False,
            'paused': False,
            'cancelled': False,
            'page_statuses': {},
            'stages': {
                'analysis': {'completed': 0, 'total': self.total_pages},
                'visualization': {'completed': 0, 'total': self.total_pages},
                'extraction': {'completed': 0, 'total': self.total_pages}
            },
            'results': {
                'successful': 0,
                'failed': 0,
                'totalImages': 0,
                'failedPages': []
            },
            'logs': []
        }

        # Initialize page statuses
        for page in range(start_page, end_page + 1):
            self.state['page_statuses'][str(page)] = 'pending'

        # Threading
        self.lock = threading.Lock()
        self.pause_event = threading.Event()
        self.pause_event.set()  # Start unpaused

        # Create batch results directory
        self.results_dir = Path("results") / f"batch_{batch_id}"
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # Log file
        self.log_file = self.results_dir / "batch_processing.log"

    def log_message(self, message, level='info'):
        """Add a log message to the state"""
        timestamp = datetime.now().isoformat()
        log_entry = {
            'timestamp': timestamp,
            'level': level,
            'message': message
        }

        with self.lock:
            self.state['logs'].append(log_entry)
            # Keep only last 100 log entries in memory
            if len(self.state['logs']) > 100:
                self.state['logs'] = self.state['logs'][-100:]

        # Also write to log file
        with open(self.log_file, 'a') as f:
            f.write(f"[{timestamp}] [{level.upper()}] {message}\n")

        logger.info(f"[{level}] {message}")

    def update_page_status(self, page_num, status):
        """Update the status of a specific page"""
        with self.lock:
            self.state['page_statuses'][str(page_num)] = status

    def update_stage_progress(self, stage, increment=1):
        """Update progress for a specific stage"""
        with self.lock:
            self.state['stages'][stage]['completed'] += increment

    def process_page(self, page_num):
        """Process a single page through all stages"""
        try:
            # Check if paused or cancelled
            self.pause_event.wait()
            if self.state['cancelled']:
                return False

            self.log_message(f"Starting processing for page {page_num}")
            self.update_page_status(page_num, 'processing')

            # Stage 1: Analysis
            if not self.run_analyzer(page_num):
                raise Exception("Analyzer failed")
            self.update_stage_progress('analysis')

            # Check if paused or cancelled
            self.pause_event.wait()
            if self.state['cancelled']:
                return False

            # Stage 2: Visualization
            if not self.run_visualizer(page_num):
                raise Exception("Visualizer failed")
            self.update_stage_progress('visualization')

            # Check if paused or cancelled
            self.pause_event.wait()
            if self.state['cancelled']:
                return False

            # Stage 3: Extraction
            image_count = self.run_extractor(page_num)
            self.update_stage_progress('extraction')

            # Update results
            with self.lock:
                self.state['results']['successful'] += 1
                self.state['results']['totalImages'] += image_count
                self.state['processed'] += 1

            self.update_page_status(page_num, 'completed')
            self.log_message(f"Successfully processed page {page_num}", 'success')

            return True

        except Exception as e:
            # Handle failure
            with self.lock:
                self.state['results']['failed'] += 1
                self.state['results']['failedPages'].append({
                    'pageNum': page_num,
                    'reason': str(e)
                })
                self.state['processed'] += 1

            self.update_page_status(page_num, 'failed')
            self.log_message(f"Failed to process page {page_num}: {str(e)}", 'error')

            return False

    def run_analyzer(self, page_num):
        """Run the analyzer for a specific page"""
        try:
            # Use standard results directory for analyzer output
            output_base = Path("results") / f"output"

            command = [
                "python", "analyzer.py",
                "--image", self.pdf_file,
                "--page", str(page_num),
                "--output", str(output_base),
                "--start-page", str(page_num),
                "--end-page", str(page_num)
            ]

            self.log_message(f"Running analyzer for page {page_num}")

            # Run the command
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            # Send "n" to bypass prompts
            stdout, stderr = process.communicate(input="n\n", timeout=300)  # 5 minute timeout

            if process.returncode != 0:
                raise Exception(f"Analyzer failed: {stderr}")

            # Copy doctags to batch directory for archiving
            doctags_src = Path("results") / "output.doctags.txt"
            doctags_dst = self.results_dir / f"page_{page_num}.doctags.txt"
            if doctags_src.exists():
                shutil.copy2(doctags_src, doctags_dst)
                self.log_message(f"DocTags saved for page {page_num}")
            else:
                raise Exception("DocTags file not generated")

            return True

        except Exception as e:
            self.log_message(f"Analyzer error for page {page_num}: {str(e)}", 'error')
            return False

    def run_visualizer(self, page_num):
        """Run the visualizer for a specific page"""
        try:
            # The visualizer expects doctags in the standard location
            doctags_path = Path("results") / "output.doctags.txt"

            # First, ensure we have the right doctags file for this page
            page_doctags = self.results_dir / f"page_{page_num}.doctags.txt"
            if page_doctags.exists():
                shutil.copy2(page_doctags, doctags_path)

            command = [
                "python", "visualizer.py",
                "--doctags", str(doctags_path),
                "--pdf", self.pdf_file,
                "--page", str(page_num)
            ]

            if self.options.get('adjust', True):
                command.append("--adjust")

            self.log_message(f"Running visualizer for page {page_num}")

            # Run the command
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )

            if process.returncode != 0:
                raise Exception(f"Visualizer failed: {process.stderr}")

            # The visualizer should have created the file in results/
            viz_src = Path("results") / f"visualization_page_{page_num}.png"
            viz_dst = self.results_dir / f"visualization_page_{page_num}.png"

            if viz_src.exists():
                shutil.copy2(viz_src, viz_dst)
                self.log_message(f"Visualization saved for page {page_num}")
            else:
                self.log_message(f"Warning: Visualization file not found for page {page_num}", 'warning')

            return True

        except Exception as e:
            self.log_message(f"Visualizer error for page {page_num}: {str(e)}", 'error')
            return False

    def run_extractor(self, page_num):
        """Run the picture extractor for a specific page"""
        try:
            # Ensure we have the right doctags file for this page
            doctags_path = Path("results") / "output.doctags.txt"
            page_doctags = self.results_dir / f"page_{page_num}.doctags.txt"
            if page_doctags.exists():
                shutil.copy2(page_doctags, doctags_path)

            # Let extractor create files in its default location first
            command = [
                "python", "picture_extractor.py",
                "--doctags", str(doctags_path),
                "--pdf", self.pdf_file,
                "--page", str(page_num)
            ]

            if self.options.get('adjust', True):
                command.append("--adjust")

            self.log_message(f"Running extractor for page {page_num}")

            # Run the command
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=300
            )

            if process.returncode != 0:
                self.log_message(f"Extractor warning for page {page_num}: {process.stderr}", 'warning')

            # Count and copy extracted images
            image_count = 0
            pics_src = Path("results") / "pictures"
            pics_dst = self.results_dir / f"pictures_page_{page_num}"

            if pics_src.exists():
                # Copy to batch directory
                if pics_dst.exists():
                    shutil.rmtree(pics_dst)
                shutil.copytree(pics_src, pics_dst)

                # Also copy to page-specific location for web interface
                pics_web = Path("results") / f"pictures_page_{page_num}"
                if pics_web.exists():
                    shutil.rmtree(pics_web)
                shutil.copytree(pics_src, pics_web)

                # Count PNG files
                image_count = len(list(pics_dst.glob("*.png")))
                self.log_message(f"Extracted {image_count} images from page {page_num}")
            else:
                self.log_message(f"No images extracted from page {page_num}", 'info')

            return image_count

        except Exception as e:
            self.log_message(f"Extractor error for page {page_num}: {str(e)}", 'error')
            return 0

    def run(self):
        """Main batch processing loop"""
        try:
            self.state['status'] = 'processing'
            self.log_message(f"Starting batch processing for {self.pdf_file} (pages {self.start_page}-{self.end_page})")

            # Determine number of workers
            max_workers = 4 if self.options.get('parallel', True) else 1

            # Create page list
            pages = list(range(self.start_page, self.end_page + 1))

            # Process pages
            if max_workers > 1:
                # Parallel processing
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {executor.submit(self.process_page, page): page for page in pages}

                    for future in as_completed(futures):
                        if self.state['cancelled']:
                            executor.shutdown(wait=False)
                            break

                        page = futures[future]
                        try:
                            future.result()
                        except Exception as e:
                            self.log_message(f"Unexpected error processing page {page}: {str(e)}", 'error')
            else:
                # Sequential processing
                for page in pages:
                    if self.state['cancelled']:
                        break
                    self.process_page(page)

            # Generate report if requested
            if self.options.get('generate_report', True) and not self.state['cancelled']:
                self.generate_report()

            # Update final state
            with self.lock:
                self.state['completed'] = True
                self.state['status'] = 'cancelled' if self.state['cancelled'] else 'completed'

            duration = time.time() - self.state['start_time']
            self.log_message(f"Batch processing completed in {self.format_duration(duration)}", 'success')

        except Exception as e:
            self.log_message(f"Critical error in batch processing: {str(e)}", 'error')
            with self.lock:
                self.state['completed'] = True
                self.state['status'] = 'error'

    def generate_report(self):
        """Generate a comprehensive HTML report"""
        try:
            self.log_message("Generating batch processing report")

            report_path = self.results_dir / "report.html"

            # Calculate statistics
            duration = time.time() - self.state['start_time']
            success_rate = (self.state['results']['successful'] / self.total_pages * 100) if self.total_pages > 0 else 0

            html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Batch Processing Report - {self.pdf_file}</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
        .container {{ max-width: 1200px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
        h1 {{ color: #2c3e50; margin-bottom: 10px; }}
        .subtitle {{ color: #7f8c8d; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin: 30px 0; }}
        .stat-box {{ background: #ecf0f1; padding: 20px; border-radius: 8px; text-align: center; }}
        .stat-value {{ font-size: 2.5em; font-weight: bold; color: #2c3e50; }}
        .stat-label {{ color: #7f8c8d; margin-top: 5px; }}
        .success {{ color: #27ae60; }}
        .error {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; text-align: left; border-bottom: 1px solid #ecf0f1; }}
        th {{ background: #34495e; color: white; }}
        tr:hover {{ background: #f8f9fa; }}
        .page-preview {{ display: inline-block; margin: 10px; text-align: center; }}
        .page-preview img {{ max-width: 200px; max-height: 200px; border: 1px solid #ddd; }}
        .failed-section {{ background: #fee; padding: 20px; border-radius: 8px; margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Batch Processing Report</h1>
        <p class="subtitle">Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
        
        <div class="stats">
            <div class="stat-box">
                <div class="stat-value">{self.total_pages}</div>
                <div class="stat-label">Total Pages</div>
            </div>
            <div class="stat-box">
                <div class="stat-value success">{self.state['results']['successful']}</div>
                <div class="stat-label">Successful</div>
            </div>
            <div class="stat-box">
                <div class="stat-value error">{self.state['results']['failed']}</div>
                <div class="stat-label">Failed</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{self.state['results']['totalImages']}</div>
                <div class="stat-label">Images Extracted</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{self.format_duration(duration)}</div>
                <div class="stat-label">Processing Time</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{success_rate:.1f}%</div>
                <div class="stat-label">Success Rate</div>
            </div>
        </div>
        
        <h2>Processing Details</h2>
        <table>
            <tr>
                <th>Parameter</th>
                <th>Value</th>
            </tr>
            <tr>
                <td>PDF File</td>
                <td>{self.pdf_file}</td>
            </tr>
            <tr>
                <td>Page Range</td>
                <td>{self.start_page} - {self.end_page}</td>
            </tr>
            <tr>
                <td>Batch ID</td>
                <td>{self.batch_id}</td>
            </tr>
            <tr>
                <td>Parallel Processing</td>
                <td>{'Enabled' if self.options.get('parallel', True) else 'Disabled'}</td>
            </tr>
            <tr>
                <td>Auto-adjust Coordinates</td>
                <td>{'Enabled' if self.options.get('adjust', True) else 'Disabled'}</td>
            </tr>
        </table>
"""

            # Add failed pages section if any
            if self.state['results']['failedPages']:
                html += """
        <div class="failed-section">
            <h2>Failed Pages</h2>
            <table>
                <tr>
                    <th>Page Number</th>
                    <th>Reason</th>
                </tr>
"""
                for failed in self.state['results']['failedPages']:
                    html += f"""
                <tr>
                    <td>{failed['pageNum']}</td>
                    <td>{failed['reason']}</td>
                </tr>
"""
                html += """
            </table>
        </div>
"""

            # Add successful pages preview
            html += """
        <h2>Processed Pages</h2>
        <div style="display: flex; flex-wrap: wrap; gap: 20px;">
"""

            for page in range(self.start_page, self.end_page + 1):
                if self.state['page_statuses'].get(str(page)) == 'completed':
                    viz_path = f"visualization_page_{page}.png"
                    html += f"""
            <div class="page-preview">
                <a href="{viz_path}" target="_blank">
                    <img src="{viz_path}" alt="Page {page}">
                </a>
                <p>Page {page}</p>
            </div>
"""

            html += """
        </div>
    </div>
</body>
</html>
"""

            with open(report_path, 'w') as f:
                f.write(html)

            self.log_message("Report generated successfully")

        except Exception as e:
            self.log_message(f"Error generating report: {str(e)}", 'error')

    def pause(self):
        """Pause the batch processing"""
        self.pause_event.clear()
        self.state['paused'] = True
        self.log_message("Batch processing paused")

    def resume(self):
        """Resume the batch processing"""
        self.pause_event.set()
        self.state['paused'] = False
        self.log_message("Batch processing resumed")

    def cancel(self):
        """Cancel the batch processing"""
        self.state['cancelled'] = True
        self.pause_event.set()  # Ensure not stuck on pause
        self.log_message("Batch processing cancelled")

    def get_state(self):
        """Get the current state with calculated fields"""
        with self.lock:
            state = self.state.copy()

            # Calculate ETA
            if state['processed'] > 0 and not state['completed']:
                elapsed = time.time() - state['start_time']
                rate = state['processed'] / elapsed
                remaining = state['total'] - state['processed']
                eta = remaining / rate if rate > 0 else 0
                state['eta'] = eta * 1000  # Convert to milliseconds
            else:
                state['eta'] = 0

            return state

    def format_duration(self, seconds):
        """Format duration in seconds to human readable format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes}:{secs:02d}"

    def create_zip_archive(self):
        """Create a ZIP archive of all results"""
        try:
            zip_path = self.results_dir / f"batch_results_{self.batch_id}.zip"

            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Add all files in the results directory
                for file_path in self.results_dir.rglob('*'):
                    if file_path.is_file() and file_path != zip_path:
                        arcname = file_path.relative_to(self.results_dir)
                        zipf.write(file_path, arcname)

            self.log_message(f"Created ZIP archive: {zip_path}")
            return zip_path

        except Exception as e:
            self.log_message(f"Error creating ZIP archive: {str(e)}", 'error')
            return None


# Global batch processors storage
batch_processors = {}
batch_lock = threading.Lock()


def start_batch_processing(batch_id, pdf_file, start_page, end_page, options):
    """Start a new batch processing job"""
    try:
        processor = BatchProcessor(batch_id, pdf_file, start_page, end_page, options)

        with batch_lock:
            batch_processors[batch_id] = processor

        # Start processing in a separate thread
        thread = threading.Thread(target=processor.run)
        thread.daemon = True
        thread.start()

        return True

    except Exception as e:
        logger.error(f"Error starting batch processing: {str(e)}")
        return False


def get_batch_processor(batch_id):
    """Get a batch processor by ID"""
    with batch_lock:
        return batch_processors.get(batch_id)


def cleanup_old_batches(max_age_hours=24):
    """Clean up old batch processors"""
    current_time = time.time()
    max_age_seconds = max_age_hours * 3600

    with batch_lock:
        to_remove = []
        for batch_id, processor in batch_processors.items():
            if processor.state['completed']:
                age = current_time - processor.state['start_time']
                if age > max_age_seconds:
                    to_remove.append(batch_id)

        for batch_id in to_remove:
            del batch_processors[batch_id]