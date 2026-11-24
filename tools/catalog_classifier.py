"""Compatibility import for existing scripts."""
from fitboy.catalog import catalog_classifier as _implementation
import sys
sys.modules[__name__] = _implementation
