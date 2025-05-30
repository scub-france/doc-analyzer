#!/usr/bin/env python3
"""
Configuration settings for DocTags
"""

import os
from pathlib import Path

# Application settings
APP_NAME = "DocTags Intelligence Suite"
APP_VERSION = "1.0.0"
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# Server settings
HOST = '127.0.0.1'
PORT = 5000
MAX_CONTENT_LENGTH = 100 * 1024 * 1024  # 100MB

# Processing settings
DEFAULT_DPI = 200
PREVIEW_DPI = 150
DEFAULT_GRID_SIZE = 500
MAX_IMAGE_WIDTH = 1200
DEFAULT_PAGE = 1
PROCESSING_TIMEOUT = 300  # 5 minutes
BATCH_WORKERS = 4

# File settings
ALLOWED_EXTENSIONS = {'pdf'}
RESULTS_DIR = 'results'
UPLOAD_DIR = 'uploads'
TEMP_DIR = 'temp_uploads'

# Cleanup settings
CLEANUP_AGE_HOURS = 24
CLEANUP_INTERVAL = 3600  # 1 hour

# Model settings
MODEL_PATH = "ds4sd/SmolDocling-256M-preview-mlx-bf16"
MAX_TOKENS = 4096

# Zone colors for visualization
ZONE_COLORS = {
    'section_header_level_1': (255, 87, 34),   # Orange
    'text': (33, 150, 243),                    # Blue
    'picture': (76, 175, 80),                  # Green
    'table': (156, 39, 176),                   # Purple
    'page_header': (255, 193, 7),              # Amber
    'page_footer': (121, 85, 72),              # Brown
    'default': (96, 125, 139)                  # Blue Grey
}

# Logging configuration
LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'default',
        },
    },
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
    },
}