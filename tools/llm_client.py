"""Compatibility import for existing scripts."""
from fitboy.metadata import llm_client as _implementation
import sys
sys.modules[__name__] = _implementation
