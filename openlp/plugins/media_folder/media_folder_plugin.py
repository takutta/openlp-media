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
The Media Folder plugin
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
from openlp.plugins.media_folder.lib.mediaitem import MediaFolderMediaItem


log = logging.getLogger(__name__)


class MediaFolderPlugin(Plugin):
    """
    The media folder plugin plays back the audio and video files found in a folder on disk.
    """
    log.info('{name} MediaFolderPlugin loaded'.format(name=__name__))

    def __init__(self):
        # The plugin keeps its settings and translations to itself, so that the core of OpenLP needs no changes
        Settings.extend_default_settings({'media_folder/status': PluginStatus.Inactive})
        install_translator(LIBRARY_TRANSLATIONS_PATH)
        install_translator(Path(__file__).parent / 'i18n')
        super().__init__('media_folder', MediaFolderMediaItem)
        self.weight = -6
        self.icon_path = UiIcons().video
        self.icon = build_icon(self.icon_path)
        # passed with drag and drop messages
        self.dnd_id = 'MediaFolder'
        State().add_service(self.name, self.weight, requires='mediacontroller', is_plugin=True)
        State().update_pre_conditions(self.name, self.check_pre_conditions())

    def check_pre_conditions(self):
        """
        Check the plugin can run and the media controller is available.
        """
        return State().is_module_active('mediacontroller')

    @staticmethod
    def about():
        """
        Return the about text for the plugin manager
        """
        about_text = translate('MediaFolderPlugin', '<strong>Media Folder Plugin</strong>'
                               '<br />The media folder plugin plays the audio and video files of a folder on disk. '
                               'The folders and files on disk are the library, so no database is used.')
        return about_text

    def set_plugin_text_strings(self):
        """
        Called to define all translatable texts of the plugin
        """
        # Name PluginList
        self.text_strings[StringContent.Name] = {
            'singular': translate('MediaFolderPlugin', 'Media Folder', 'name singular'),
            'plural': translate('MediaFolderPlugin', 'Media Folder', 'name plural')
        }
        # Name for MediaDockManager, SettingsManager
        self.text_strings[StringContent.VisibleName] = {
            'title': translate('MediaFolderPlugin', 'Media Folder', 'container title')
        }
        # Middle Header Bar
        tooltips = {
            'load': translate('MediaFolderPlugin', 'Copy media files into the folder.'),
            'import': '',
            'new': '',
            'edit': '',
            'delete': translate('MediaFolderPlugin', 'Move the selected media to the trash.'),
            'preview': translate('MediaFolderPlugin', 'Preview the selected media.'),
            'live': translate('MediaFolderPlugin', 'Send the selected media live.'),
            'service': translate('MediaFolderPlugin', 'Add the selected media to the service.')
        }
        self.set_plugin_ui_text_strings(tooltips)
