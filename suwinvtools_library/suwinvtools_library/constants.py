import os
from pathlib import Path

# This file is suwinvtools_library/suwinvtools_library/constants.py.
# Three directories up from there is the solution root (it contains all sub-projects).
# The fallback only holds for editable path installs (how every project here depends on
# the library). A wheel install lands in site-packages, so override with SUWINVTOOLS_SOLUTION_ROOT.
SOLUTION_ROOT = (
    Path(os.environ["SUWINVTOOLS_SOLUTION_ROOT"]) if "SUWINVTOOLS_SOLUTION_ROOT" in os.environ else Path(__file__).parent.parent.parent
)
