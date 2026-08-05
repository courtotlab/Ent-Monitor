from pathlib import Path

def get_run_dir(run_id: str, layer_folder: str) -> Path:
  """Returns the output directory for a specific run ID and layer."""
  return Path("results") / layer_folder / run_id

def get_results_dir(layer_folder: str = "") -> Path:
  """Returns the base results directory, optionally for a specific layer."""
  base = Path("results")
  return base / layer_folder if layer_folder else base
