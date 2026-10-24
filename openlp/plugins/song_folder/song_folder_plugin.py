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
The Song Folder plugin
"""
import logging
from pathlib import Path

from openlp.core.common.enum import PluginStatus
from openlp.core.common.i18n import translate
from openlp.core.common.settings import Settings
from openlp.core.lib import build_icon
from openlp.core.lib.plugin import Plugin, StringContent
from openlp.core.state import State
from openlp.core.ui.icons import UiIcons

from openlp.plugins.filesystem_library.translations import LIBRARY_TRANSLATIONS_PATH, install_translator
from openlp.plugins.song_folder.lib.mediaitem import SongFolderMediaItem
from openlp.plugins.songs.lib.songstab import SongsTab
from openlp.plugins.songs.songsplugin import song_footer


log = logging.getLogger(__name__)


class SongFolderPlugin(Plugin):
    """
    The song folder plugin shows the songs of a folder on disk. Each song is an OpenLyrics file.
    """
    log.info('{name} SongFolderPlugin loaded'.format(name=__name__))

    def __init__(self):
        # The plugin keeps its settings and translations to itself, so that the core of OpenLP needs no changes.
        # The footer template of the Songs plugin is used, so its default is needed even if the Songs plugin is off.
        Settings.extend_default_settings({'song_folder/status': PluginStatus.Inactive, **song_footer})
        install_translator(LIBRARY_TRANSLATIONS_PATH)
        install_translator(Path(__file__).parent / 'i18n')
        # The settings of the Songs plugin (upper case, first slide, chords, footer etc.) are shared, so its settings
        # tab is used
        super().__init__('song_folder', SongFolderMediaItem, SongsTab)
        self.weight = -9
        self.icon_path = UiIcons().music
        self.icon = build_icon(self.icon_path)
        # passed with drag and drop messages
        self.dnd_id = 'SongFolder'
        State().add_service(self.name, self.weight, is_plugin=True)
        State().update_pre_conditions(self.name, self.check_pre_conditions())

    @staticmethod
    def about():
        """
        Return the about text for the plugin manager
        """
        about_text = translate('SongFolderPlugin', '<strong>Song Folder Plugin</strong>'
                               '<br />The song folder plugin shows the OpenLyrics songs of a folder on disk. '
                               'The folders and files on disk are the library, so no database is used.')
        return about_text

    def set_plugin_text_strings(self):
        """
        Called to define all translatable texts of the plugin
        """
        # Name PluginList
        self.text_strings[StringContent.Name] = {
            'singular': translate('SongFolderPlugin', 'Song Folder', 'name singular'),
            'plural': translate('SongFolderPlugin', 'Song Folder', 'name plural')
        }
        # Name for MediaDockManager, SettingsManager
        self.text_strings[StringContent.VisibleName] = {
            'title': translate('SongFolderPlugin', 'Song Folder', 'container title')
        }
        # Middle Header Bar
        tooltips = {
            'load': translate('SongFolderPlugin', 'Copy OpenLyrics files into the folder.'),
            'import': '',
            'new': translate('SongFolderPlugin', 'Add a new song.'),
            'edit': translate('SongFolderPlugin', 'Edit the selected song.'),
            'delete': translate('SongFolderPlugin', 'Move the selected songs to the trash.'),
            'preview': translate('SongFolderPlugin', 'Preview the selected song.'),
            'live': translate('SongFolderPlugin', 'Send the selected song live.'),
            'service': translate('SongFolderPlugin', 'Add the selected song to the service.')
        }
        self.set_plugin_ui_text_strings(tooltips)
