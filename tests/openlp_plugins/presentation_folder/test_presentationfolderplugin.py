# -*- coding: utf-8 -*-

##########################################################################
# OpenLP - Open Source Lyrics Projection                                 #
# ---------------------------------------------------------------------- #
# Copyright (c) 2008 OpenLP Developers                                   #
# ---------------------------------------------------------------------- #
# This program is free software: you can redistribute it and/or modify   #
# it under the terms of the GNU General Public License as published by   #
# the Free Software Foundation, either version 3 of the License, or      #
# (at your option) any later version.                                    #
#                                                                        #
# This program is distributed in the hope that it will be useful,        #
# but WITHOUT ANY WARRANTY; without even the implied warranty of         #
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the          #
# GNU General Public License for more details.                           #
#                                                                        #
# You should have received a copy of the GNU General Public License      #
# along with this program.  If not, see <https://www.gnu.org/licenses/>. #
##########################################################################
"""
Test the presentation folder plugin
"""
from pathlib import Path
from unittest.mock import patch

from openlp.core.common.enum import PluginStatus
from openlp.core.common.registry import Registry
from openlp.core.common.settings import Settings
from openlp.plugins.presentation_folder.presentation_folder_plugin import PresentationFolderPlugin


def test_plugin_registers_itself(state, settings, temp_folder):
    """The plugin can be found under the names the State and the service manager use, and finds the controllers"""
    with patch('openlp.plugins.presentation_folder.presentation_folder_plugin.AppLocation.get_section_data_path',
               side_effect=lambda section: Path(temp_folder) / section):
        plugin = PresentationFolderPlugin()

    assert plugin.name == 'presentation_folder'
    assert Registry().get('presentation_folder_plugin') is plugin
    assert plugin.status == PluginStatus.Inactive
    assert 'Pdf' in plugin.controllers
    assert plugin.check_pre_conditions() is True


def test_controllers_use_plugin_data_folder(state, settings, temp_folder):
    """The thumbnails are kept where the core looks for them when a service file is opened"""
    with patch('openlp.plugins.presentation_folder.presentation_folder_plugin.AppLocation.get_section_data_path',
               side_effect=lambda section: Path(temp_folder) / section):
        plugin = PresentationFolderPlugin()

    controller = plugin.controllers['Pdf']
    assert controller.thumbnail_folder == Path(temp_folder) / 'presentation_folder' / 'thumbnails'
    assert controller.temp_folder == Path(temp_folder) / 'presentation_folder' / 'Pdf'
    assert controller.thumbnail_folder.is_dir()


def test_plugin_adds_its_own_default_settings(state, settings, temp_folder):
    """The plugin does not need its status in the default settings of the core"""
    Settings.__default_settings__.pop('presentation_folder/status', None)

    with patch('openlp.plugins.presentation_folder.presentation_folder_plugin.AppLocation.get_section_data_path',
               side_effect=lambda section: Path(temp_folder) / section):
        plugin = PresentationFolderPlugin()

    assert Settings.__default_settings__['presentation_folder/status'] == PluginStatus.Inactive
    assert plugin.status == PluginStatus.Inactive


def test_about_text():
    """The about text is not empty"""
    assert PresentationFolderPlugin.about()
