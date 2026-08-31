"""Layer 1 - Ingestion"""

import logging
import sys
from pathlib import Path

# Define the log file path inside the ingestion folder
_log_file = Path(__file__).parent / "ingestion.log"

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

# Configure the base logger for the entire layers.ingestion package
_ingestion_logger = logging.getLogger("layers.ingestion")
_ingestion_logger.setLevel(logging.INFO)

# Prevent adding multiple handlers if the module is imported multiple times
if not _ingestion_logger.handlers:
  _ingestion_logger.addHandler(_file_handler)
  _ingestion_logger.addHandler(_stream_handler)
  _ingestion_logger.propagate = False

  # Route Apify SDK logs into the same ingestion.log file
  _apify_logger = logging.getLogger("apify_client")
  _apify_logger.setLevel(logging.INFO)
  _apify_logger.addHandler(_file_handler)
  _apify_logger.addHandler(_stream_handler)
  _apify_logger.propagate = False
