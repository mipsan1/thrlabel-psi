import os
import sys

# Make the repo-root modules (sim.py, attack.py, ...) importable from tests.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
