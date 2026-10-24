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
Test the media folder plugin
"""
from openlp.core.common.enum import PluginStatus
from openlp.core.common.registry import Registry
from openlp.core.common.settings import Settings
from openlp.core.state import State
from openlp.plugins.media_folder.media_folder_plugin import MediaFolderPlugin


def test_plugin_registers_itself(state, settings):
    """The plugin can be found under the names the State and the service manager use"""
    # GIVEN: An active media controller
    State().add_service('mediacontroller', 0)
    State().update_pre_conditions('mediacontroller', True)

    # WHEN: The plugin is created
    plugin = MediaFolderPlugin()

    # THEN: It is registered, and keeps its saved status
    assert plugin.name == 'media_folder'
    assert Registry().get('media_folder_plugin') is plugin
    assert plugin.status == PluginStatus.Inactive
    assert plugin.check_pre_conditions() is True


def test_plugin_adds_its_own_default_settings(state, settings):
    """The plugin does not need its status in the default settings of the core"""
    # GIVEN: Default settings without the status of the plugin
    Settings.__default_settings__.pop('media_folder/status', None)
    State().add_service('mediacontroller', 0)
    State().update_pre_conditions('mediacontroller', True)

    # WHEN: The plugin is created
    plugin = MediaFolderPlugin()

    # THEN: The plugin added the default itself
    assert Settings.__default_settings__['media_folder/status'] == PluginStatus.Inactive
    assert plugin.status == PluginStatus.Inactive


def test_plugin_disabled_without_media_controller(state, settings):
    """Without a media controller the plugin is disabled"""
    State().add_service('mediacontroller', 0)
    State().update_pre_conditions('mediacontroller', False)
    State().modules['mediacontroller'].status = PluginStatus.Inactive

    plugin = MediaFolderPlugin()

    assert plugin.status == PluginStatus.Disabled


def test_about_text():
    """The about text is not empty"""
    assert MediaFolderPlugin.about()
