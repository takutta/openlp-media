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
The Image Folder plugin
"""
import logging
from pathlib import Path

from openlp.core.common.enum import ImageThemeMode, PluginStatus
from openlp.core.common.i18n import translate
from openlp.core.common.settings import Settings
from openlp.core.lib import build_icon
from openlp.core.lib.plugin import Plugin, StringContent
from openlp.core.state import State
from openlp.core.ui.icons import UiIcons

from ..filesystem_library.translations import LIBRARY_TRANSLATIONS_PATH, install_translator
from .lib.imagetab import ImageFolderTab
from .lib.mediaitem import ImageFolderMediaItem


log = logging.getLogger(__name__)


class ImageFolderPlugin(Plugin):
    """
    The image folder plugin shows the images found in a folder on disk.
    """
    log.info('{name} ImageFolderPlugin loaded'.format(name=__name__))

    def __init__(self):
        # The plugin keeps its settings and translations to itself, so that the core of OpenLP needs no changes
        Settings.extend_default_settings({
            'image_folder/status': PluginStatus.Inactive,
            'image_folder/background mode': ImageThemeMode.Black,
            'image_folder/theme': None,
        })
        install_translator(LIBRARY_TRANSLATIONS_PATH)
        install_translator(Path(__file__).parent / 'i18n')
        super().__init__('image_folder', ImageFolderMediaItem, ImageFolderTab)
        self.weight = -7
        self.icon_path = UiIcons().picture
        self.icon = build_icon(self.icon_path)
        # passed with drag and drop messages
        self.dnd_id = 'ImageFolder'
        State().add_service(self.name, self.weight, is_plugin=True)
        State().update_pre_conditions(self.name, self.check_pre_conditions())

    @staticmethod
    def about():
        """
        Return the about text for the plugin manager
        """
        about_text = translate('ImageFolderPlugin', '<strong>Image Folder Plugin</strong>'
                               '<br />The image folder plugin shows the images of a folder on disk. Several images '
                               'or a whole folder can be added to the service as one item, which can be looped as '
                               'a slide show. Images can also replace the background of the live display. '
                               'The folders and files on disk are the library, so no database is used.')
        return about_text

    def set_plugin_text_strings(self):
        """
        Called to define all translatable texts of the plugin
        """
        # Name PluginList
        self.text_strings[StringContent.Name] = {
            'singular': translate('ImageFolderPlugin', 'Image Folder', 'name singular'),
            'plural': translate('ImageFolderPlugin', 'Images', 'name plural')
        }
        # Name for MediaDockManager, SettingsManager
        self.text_strings[StringContent.VisibleName] = {
            'title': translate('ImageFolderPlugin', 'Image Folder', 'container title')
        }
        # Middle Header Bar
        tooltips = {
            'load': translate('ImageFolderPlugin', 'Copy images into the folder.'),
            'import': '',
            'new': '',
            'edit': '',
            'delete': translate('ImageFolderPlugin', 'Move the selected images to the trash.'),
            'preview': translate('ImageFolderPlugin', 'Preview the selected images.'),
            'live': translate('ImageFolderPlugin', 'Send the selected images live.'),
            'service': translate('ImageFolderPlugin', 'Add the selected images to the service.')
        }
        self.set_plugin_ui_text_strings(tooltips)
