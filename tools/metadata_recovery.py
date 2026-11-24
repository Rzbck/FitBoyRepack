"""Compatibility import for existing scripts."""
from fitboy.metadata import metadata_recovery as _implementation
import sys
sys.modules[__name__] = _implementation
