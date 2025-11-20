import sys
import os
from pathlib import Path

# Ensure project root is on sys.path for imports
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Set required environment variables for tests
os.environ.setdefault("GPT_KEY", "test-key")
