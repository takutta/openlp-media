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
Test the song folder plugin
"""
from openlp.core.common.enum import PluginStatus
from openlp.core.common.registry import Registry
from openlp.core.common.settings import Settings
from openlp.plugins.song_folder.song_folder_plugin import SongFolderPlugin


def test_plugin_registers_itself(state, settings):
    """The plugin can be found under the names the State and the service manager use"""
    plugin = SongFolderPlugin()

    assert plugin.name == 'song_folder'
    assert Registry().get('song_folder_plugin') is plugin
    assert plugin.status == PluginStatus.Inactive
    assert plugin.check_pre_conditions() is True


def test_plugin_adds_its_own_default_settings(state, settings):
    """The plugin does not need its status or the footer template in the default settings of the core"""
    Settings.__default_settings__.pop('song_folder/status', None)
    Settings.__default_settings__.pop('songs/footer template', None)

    SongFolderPlugin()

    assert Settings.__default_settings__['song_folder/status'] == PluginStatus.Inactive
    assert '${title}' in Settings.__default_settings__['songs/footer template']


def test_about_text():
    """The about text is not empty"""
    assert SongFolderPlugin.about()
