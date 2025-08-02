# -*- coding: utf-8 -*-

"""
This file makes the 'modals' directory a Python package and exposes key Modal classes
for easier importing elsewhere in the application.
"""

from .tag_modal import TagModal
from .path_modal import PathModal
from .template_modal import TemplateModal

__all__ = [
    "TagModal",
    "PathModal",
    "TemplateModal"
]