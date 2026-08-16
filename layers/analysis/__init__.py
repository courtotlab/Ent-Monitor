"""Layer 3 - Analysis (Agentic Classification)"""

import logging
from pathlib import Path

# Define the log file path inside the analysis folder
_log_file = Path(__file__).parent / "analysis.log"

# Create a formatter that includes time and the specific node/module name
_formatter = logging.Formatter(
  fmt="%(asctime)s | %(name)-35s | %(levelname)-7s | %(message)s",
  datefmt="%Y-%m-%d %H:%M:%S",
)

# Set up the file handler
_file_handler = logging.FileHandler(_log_file, encoding="utf-8")
_file_handler.setFormatter(_formatter)

# Configure the base logger for the entire layers.analysis package
_analysis_logger = logging.getLogger("layers.analysis")
_analysis_logger.setLevel(logging.INFO)

# Prevent adding multiple handlers if the module is imported multiple times
if not _analysis_logger.handlers:
  _analysis_logger.addHandler(_file_handler)
  _analysis_logger.propagate = True
