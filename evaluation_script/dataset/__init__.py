from .recog_dataset import *
from .end2end_dataset import *

# Detection and Md2Md datasets are optional (not needed for end2end eval)
try:
    from .detection_dataset import *
except ImportError:
    pass

try:
    from .md2md_dataset import *
except ImportError:
    pass

from registry.registry import DATASET_REGISTRY

__all__ = [
    "RecognitionFormulaDataset",
    "End2EndDataset",
]
