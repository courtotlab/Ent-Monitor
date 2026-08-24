"""Layer 2 - Preprocessing"""

import logging
import sys
from pathlib import Path

# Define the log file path inside the preprocess folder
_log_file = Path(__file__).parent / "preprocess.log"

# Create a formatter that includes time and the specific node/module name
_formatter = logging.Formatter(
  fmt="%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)

# Set up the file handler
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_formatter)

# Set up the console handler
_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(_formatter)

# Configure the base logger for the entire layers.preprocess package
_preprocess_logger = logging.getLogger("layers.preprocess")
_preprocess_logger.setLevel(logging.INFO)

# Prevent adding multiple handlers if the module is imported multiple times
if not _preprocess_logger.handlers:
  _preprocess_logger.addHandler(_file_handler)
  _preprocess_logger.addHandler(_stream_handler)
  _preprocess_logger.propagate = False
