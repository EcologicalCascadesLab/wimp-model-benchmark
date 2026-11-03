"""Match class names to the display names Colin's reports use."""
import sys
from pathlib import Path

VENDOR = Path(__file__).resolve().parents[1] / "vendor" / "model-benchmark-testing-workflow"


def display_names(names):
    sys.path.insert(0, str(VENDOR))
    from src.utils import format_species_name  # noqa: E402
    return [format_species_name(n.strip().lower()) for n in names]
