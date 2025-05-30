#!/usr/bin/env python3
"""
Common utilities for DocTags processing
"""

import os
import subprocess
import logging
from pathlib import Path
from typing import Optional, Tuple, Dict, List
import pdf2image
from pdf2image.pdf2image import pdfinfo_from_path

logger = logging.getLogger(__name__)

# Configuration constants
DEFAULT_DPI = 200
DEFAULT_GRID_SIZE = 500
MAX_WIDTH = 1200
RESULTS_DIR_NAME = "results"

def get_project_root() -> Path:
    """Get the project root directory."""
    # If running from backend/page_treatment/, go up to root
    current_file = Path(__file__)
    if current_file.parent.name == 'page_treatment':
        return current_file.parent.parent.parent
    elif current_file.parent.name == 'backend':
        return current_file.parent.parent
    else:
        return Path.cwd()

def ensure_results_folder(custom_path: Optional[str] = None) -> Path:
    """Create and return the results folder path."""
    if custom_path:
        results_dir = Path(custom_path)
    else:
        results_dir = get_project_root() / RESULTS_DIR_NAME

    if not results_dir.exists():
        results_dir.mkdir(parents=True)
        logger.info(f"Created results directory: {results_dir}")

    return results_dir

def count_pdf_pages(pdf_path: str) -> int:
    """Count the number of pages in a PDF file."""
    if not os.path.exists(pdf_path):
        logger.error(f"PDF file not found: {pdf_path}")
        return 0

    try:
        info = pdfinfo_from_path(pdf_path)
        return info["Pages"]
    except Exception as e:
        logger.warning(f"pdfinfo failed: {e}, trying fallback method")
        try:
            # Fallback: convert first page to check
            images = pdf2image.convert_from_path(pdf_path, dpi=72, first_page=1, last_page=1)
            if not images:
                return 0

            # Binary search for last page
            low, high = 1, 1000
            while low < high:
                mid = (low + high + 1) // 2
                try:
                    images = pdf2image.convert_from_path(pdf_path, dpi=72, first_page=mid, last_page=mid)
                    if images:
                        low = mid
                    else:
                        high = mid - 1
                except:
                    high = mid - 1

            return low
        except Exception as e2:
            logger.error(f"Error counting PDF pages: {e2}")
            return 0

def load_pdf_page(pdf_path: str, page_num: int = 1, dpi: int = DEFAULT_DPI) -> Optional[object]:
    """Load a specific page from PDF as an image."""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    logger.info(f"Converting PDF page {page_num} to image (DPI: {dpi})...")
    try:
        pdf_images = pdf2image.convert_from_path(
            pdf_path,
            dpi=dpi,
            first_page=page_num,
            last_page=page_num
        )
        if not pdf_images:
            raise Exception(f"Could not extract page {page_num} from PDF")
        return pdf_images[0]
    except Exception as e:
        raise Exception(f"Error converting PDF to image: {e}")

def normalize_coordinates(elements: List[Dict], image_width: int, image_height: int,
                          grid_size: int = DEFAULT_GRID_SIZE) -> List[Dict]:
    """
    Normalize coordinates from DocTags grid to actual image dimensions.

    Args:
        elements: List of elements with x1, y1, x2, y2 coordinates
        image_width: Width of the image in pixels
        image_height: Height of the image in pixels
        grid_size: The grid size used in DocTags (default 500)

    Returns:
        List of elements with normalized coordinates
    """
    normalized = []
    for element in elements:
        new_element = element.copy()
        new_element['x1'] = int(element['x1'] * image_width / grid_size)
        new_element['y1'] = int(element['y1'] * image_height / grid_size)
        new_element['x2'] = int(element['x2'] * image_width / grid_size)
        new_element['y2'] = int(element['y2'] * image_height / grid_size)
        normalized.append(new_element)
    return normalized

def auto_adjust_coordinates(elements: List[Dict], image_width: int, image_height: int) -> List[Dict]:
    """
    Automatically adjust coordinates based on image dimensions.
    """
    if not elements:
        return elements

    # Find maximum coordinates
    max_x = max([el['x2'] for el in elements])
    max_y = max([el['y2'] for el in elements])

    # Check if coordinates are in normalized grid (0-500 range)
    if max_x <= DEFAULT_GRID_SIZE and max_y <= DEFAULT_GRID_SIZE:
        logger.info(f"Detected normalized coordinates (0-{DEFAULT_GRID_SIZE} grid)")
        return normalize_coordinates(elements, image_width, image_height)

    # Calculate scaling factors
    x_scale = calculate_scale_factor(max_x, image_width)
    y_scale = calculate_scale_factor(max_y, image_height)

    # Apply scaling
    adjusted = []
    for el in elements:
        adjusted_el = el.copy()
        adjusted_el['x1'] = int(el['x1'] * x_scale)
        adjusted_el['y1'] = int(el['y1'] * y_scale)
        adjusted_el['x2'] = int(el['x2'] * x_scale)
        adjusted_el['y2'] = int(el['y2'] * y_scale)
        adjusted.append(adjusted_el)

    logger.info(f"Applied auto-scaling: X={x_scale:.3f}, Y={y_scale:.3f}")
    return adjusted

def calculate_scale_factor(max_coord: float, image_size: float) -> float:
    """Calculate appropriate scaling factor."""
    if max_coord <= 0:
        return 1.0

    # If coordinates are way off, apply aggressive scaling
    if max_coord > image_size * 5 or max_coord < image_size / 5:
        return image_size / max_coord

    # Otherwise, apply conservative scaling
    if max_coord > image_size:
        return min(image_size / max_coord, 1.0)
    else:
        return max(image_size / max_coord, 0.5)

# In backend/utils.py, make sure this function exists:
def run_command_with_timeout(command: str, timeout: int = 300, input_text: str = "n\n") -> Tuple[bool, str, str]:
    """
    Run a command with timeout and return success, stdout, stderr.
    """
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

        stdout, stderr = process.communicate(input=input_text, timeout=timeout)
        success = process.returncode == 0

        return success, stdout, stderr

    except subprocess.TimeoutExpired:
        process.kill()
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)

def format_duration(seconds: float) -> str:
    """Format duration in seconds to human readable format."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"

def validate_coordinates(x1: int, y1: int, x2: int, y2: int,
                         width: int, height: int) -> bool:
    """Validate that coordinates are within bounds."""
    return (0 <= x1 < x2 <= width and
            0 <= y1 < y2 <= height)