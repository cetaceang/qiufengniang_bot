# -*- coding: utf-8 -*-

"""
This file makes the 'views' directory a Python package and exposes key View classes
for easier importing elsewhere in the application.
"""

from .main_panel import MainPanelView
from .tag_management import TagManagementView
from .path_configuration import PathConfigurationView
from .role_configuration import RoleConfigurationView
from .message_templates import MessageTemplatesView
from .deployment import DeploymentView
from .guidance_panel import GuidancePanelView
from .channel_message_config import ChannelMessageConfigView
from .channel_panel import PermanentPanelView
from .ui_elements import BackButton

__all__ = [
    "MainPanelView",
    "TagManagementView",
    "PathConfigurationView",
    "RoleConfigurationView",
    "MessageTemplatesView",
    "DeploymentView",
    "GuidancePanelView",
    "ChannelMessageConfigView",
    "PermanentPanelView",
    "BackButton"
]