"""Root conftest — adds repo root to sys.path so tests can import `backend.*`
and `tests.*` without a pip install. Matches Phase 3 Plan 03-05 requirement m10.
"""
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.resolve()
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
