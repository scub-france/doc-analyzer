#!/usr/bin/env python3
"""
Multipart File Upload Handler for DocTags
Handles file upload processing and validation
"""

import os
import time
import logging
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.datastructures import FileStorage
import tempfile
import shutil
from typing import Optional, Dict, Tuple, List

logger = logging.getLogger(__name__)

class MultipartHandler:
    """Handle multipart file uploads with validation and storage"""

    ALLOWED_EXTENSIONS = {'pdf'}
    MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
    UPLOAD_FOLDER = 'uploads'
    TEMP_FOLDER = 'temp_uploads'

    def __init__(self, upload_folder: str = None, temp_folder: str = None):
        self.upload_folder = Path(upload_folder or self.UPLOAD_FOLDER)
        self.temp_folder = Path(temp_folder or self.TEMP_FOLDER)
        self._ensure_folders()

    def _ensure_folders(self):
        """Ensure upload and temp folders exist"""
        for folder in [self.upload_folder, self.temp_folder]:
            if not folder.exists():
                folder.mkdir(parents=True)
                logger.info(f"Created folder: {folder}")

    def allowed_file(self, filename: str) -> bool:
        """Check if file extension is allowed"""
        return '.' in filename and \
            filename.rsplit('.', 1)[1].lower() in self.ALLOWED_EXTENSIONS

    def validate_file(self, file: FileStorage) -> Tuple[bool, Optional[str]]:
        """
        Validate uploaded file
        Returns: (is_valid, error_message)
        """
        if not file:
            return False, "No file provided"

        if file.filename == '':
            return False, "No file selected"

        if not self.allowed_file(file.filename):
            return False, f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_EXTENSIONS)}"

        # Check file size (if possible)
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)  # Reset file pointer

        if file_size > self.MAX_FILE_SIZE:
            return False, f"File too large. Maximum size: {self.MAX_FILE_SIZE / (1024*1024):.1f}MB"

        return True, None

    def save_uploaded_file(self, file: FileStorage, permanent: bool = True) -> Tuple[bool, Dict]:
        """
        Save uploaded file

        Args:
            file: The uploaded file
            permanent: If True, save to uploads folder; if False, save to temp folder

        Returns:
            (success, result_dict) where result_dict contains:
                - filepath: Path to saved file
                - filename: Original filename
                - unique_filename: Saved filename
                - size: File size in bytes
                - error: Error message if failed
        """
        # Validate file
        is_valid, error_msg = self.validate_file(file)
        if not is_valid:
            return False, {'error': error_msg}

        try:
            # Secure the filename
            original_filename = secure_filename(file.filename)
            timestamp = int(time.time() * 1000)  # Millisecond timestamp

            # Create unique filename
            name_parts = original_filename.rsplit('.', 1)
            if len(name_parts) == 2:
                unique_filename = f"{name_parts[0]}_{timestamp}.{name_parts[1]}"
            else:
                unique_filename = f"{original_filename}_{timestamp}"

            # Determine save location
            save_folder = self.upload_folder if permanent else self.temp_folder
            filepath = save_folder / unique_filename

            # Save file
            file.save(str(filepath))

            # Get file size
            file_size = os.path.getsize(filepath)

            logger.info(f"Saved file: {filepath} (size: {file_size} bytes)")

            return True, {
                'filepath': str(filepath),
                'filename': original_filename,
                'unique_filename': unique_filename,
                'size': file_size,
                'permanent': permanent
            }

        except Exception as e:
            logger.error(f"Error saving file: {str(e)}")
            return False, {'error': f"Failed to save file: {str(e)}"}

    def save_to_temp(self, file: FileStorage) -> Tuple[bool, Dict]:
        """Save file to temporary folder"""
        return self.save_uploaded_file(file, permanent=False)

    def move_to_permanent(self, temp_filepath: str) -> Tuple[bool, Dict]:
        """Move file from temp to permanent storage"""
        try:
            temp_path = Path(temp_filepath)
            if not temp_path.exists():
                return False, {'error': 'Temporary file not found'}

            permanent_path = self.upload_folder / temp_path.name
            shutil.move(str(temp_path), str(permanent_path))

            return True, {
                'filepath': str(permanent_path),
                'moved_from': str(temp_path)
            }
        except Exception as e:
            logger.error(f"Error moving file: {str(e)}")
            return False, {'error': f"Failed to move file: {str(e)}"}

    def cleanup_old_files(self, max_age_hours: int = 24, folder: str = 'both'):
        """
        Remove old files from upload/temp folders

        Args:
            max_age_hours: Maximum age of files in hours
            folder: 'uploads', 'temp', or 'both'
        """
        folders_to_clean = []
        if folder in ['uploads', 'both']:
            folders_to_clean.append(self.upload_folder)
        if folder in ['temp', 'both']:
            folders_to_clean.append(self.temp_folder)

        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        removed_count = 0

        for folder_path in folders_to_clean:
            if not folder_path.exists():
                continue

            for file_path in folder_path.glob('*.pdf'):
                try:
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        removed_count += 1
                        logger.info(f"Deleted old file: {file_path}")
                except Exception as e:
                    logger.error(f"Error deleting file {file_path}: {str(e)}")

        return removed_count

    def get_file_info(self, filepath: str) -> Optional[Dict]:
        """Get information about an uploaded file"""
        try:
            path = Path(filepath)
            if not path.exists():
                return None

            stats = path.stat()
            return {
                'filepath': str(path),
                'filename': path.name,
                'size': stats.st_size,
                'created': stats.st_ctime,
                'modified': stats.st_mtime,
                'exists': True
            }
        except Exception as e:
            logger.error(f"Error getting file info: {str(e)}")
            return None

    def create_multipart_response(self, success: bool, data: Dict) -> Dict:
        """Create standardized response for multipart operations"""
        response = {
            'success': success,
            'timestamp': time.time()
        }

        if success:
            response['data'] = data
        else:
            response['error'] = data.get('error', 'Unknown error')

        return response


# Create a default instance
default_handler = MultipartHandler()