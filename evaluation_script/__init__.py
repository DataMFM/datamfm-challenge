"""
DataMFM Challenge - EvalAI Evaluation Script
Uses OmniDocBench's real evaluation code.
"""
import subprocess
import sys
import os


def install(package):
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", package],
            check=True, capture_output=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Warning: failed to install {package}: {e}")


# Install required dependencies
DEPS = [
    "python-Levenshtein",
    "apted",
    "lxml",
    "beautifulsoup4",
    "pylatexenc==2.10",     # last stable release (pure Python)
    "pandas<=1.3.5",        # Python 3.7 compat
    "scipy<=1.7.3",         # Python 3.7 compat
    "func-timeout",
    "loguru",
    "tqdm",
    "tabulate",
    "pyyaml",
    "numpy<=1.21.6",        # Python 3.7 compat
]

for dep in DEPS:
    try:
        install(dep)
    except Exception:
        pass

from .main import evaluate
