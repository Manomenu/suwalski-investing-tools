import os
from pathlib import Path

# __file__ = suwalski_investing_library/suwalski_investing_library/constants.py
# .parent.parent.parent = solution root (contains all sub-projects).
# The fallback only holds for editable path installs (how every project here depends on
# the library). A wheel install lands in site-packages, so override with SUWALSKI_SOLUTION_ROOT.
SOLUTION_ROOT = (
    Path(os.environ["SUWALSKI_SOLUTION_ROOT"]) if "SUWALSKI_SOLUTION_ROOT" in os.environ else Path(__file__).parent.parent.parent
)
