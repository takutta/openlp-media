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
The Presentation Folder plugin
"""
import importlib
import logging
from pathlib import Path

from openlp.core.common.applocation import AppLocation
from openlp.core.common.enum import PluginStatus
from openlp.core.common.i18n import translate
from openlp.core.common.path import create_paths
from openlp.core.common.settings import Settings
from openlp.core.lib import build_icon
from openlp.core.lib.plugin import Plugin, StringContent
from openlp.core.lib.pluginmanager import PluginManager
from openlp.core.state import State
from openlp.core.ui.icons import UiIcons

from openlp.plugins.presentations.lib.presentationcontroller import PresentationController
from openlp.plugins.presentations.lib.presentationtab import PresentationTab
from ..filesystem_library.translations import LIBRARY_TRANSLATIONS_PATH, install_translator
from .lib.mediaitem import PresentationFolderMediaItem


log = logging.getLogger(__name__)


class PresentationFolderPlugin(Plugin):
    """
    The presentation folder plugin shows the presentations found in a folder on disk. The presentation applications
    are controlled with the controllers of the Presentation plugin, and their settings (``presentations/*``) are shared
    with it.
    """
    log.info('{name} PresentationFolderPlugin loaded'.format(name=__name__))

    def __init__(self):
        # The plugin keeps its settings and translations to itself, so that the core of OpenLP needs no changes
        Settings.extend_default_settings({'presentation_folder/status': PluginStatus.Inactive})
        install_translator(LIBRARY_TRANSLATIONS_PATH)
        install_translator(Path(__file__).parent / 'i18n')
        super().__init__('presentation_folder', PresentationFolderMediaItem)
        self.weight = -8
        self.icon_path = UiIcons().presentation
        self.icon = build_icon(self.icon_path)
        self.controllers = {}
        # passed with drag and drop messages
        self.dnd_id = 'PresentationFolder'
        State().add_service(self.name, self.weight, is_plugin=True)
        State().update_pre_conditions(self.name, self.check_pre_conditions())

    def create_settings_tab(self, parent):
        """
        Create the settings tab. It is the tab of the Presentation plugin, which edits the shared controller settings.

        :param parent: parent UI Element
        """
        visible_name = self.get_string(StringContent.VisibleName)
        self.settings_tab = PresentationTab(parent, self.name, visible_name['title'], self.controllers, self.icon_path)

    def create_media_manager_item(self):
        """
        Create the media manager item
        """
        self.media_item = PresentationFolderMediaItem(self.main_window.media_dock_manager.media_dock, self,
                                                      self.controllers)

    def initialise(self):
        """
        Start the processes of the enabled presentation applications
        """
        log.info('Presentation Folder Initialising')
        super().initialise()
        for controller in self.controllers.values():
            if controller.enabled():
                try:
                    controller.start_process()
                except Exception:
                    log.exception('Failed to start controller process')
                    controller.available = False
        self.media_item.build_file_mask_string()

    def finalise(self):
        """
        Ask the enabled presentation applications to close down
        """
        log.info('Plugin Finalise')
        for controller in self.controllers.values():
            if controller.enabled():
                controller.kill()
        super().finalise()

    def register_controller(self, controller: PresentationController):
        """
        Store a presentation controller. The thumbnails and the temporary files of the controller are kept in the data
        folder of this plugin, because that is where the core puts the thumbnails of a service file it opens.

        :param controller: The controller to store
        """
        data_path = AppLocation.get_section_data_path(self.name)
        controller.temp_folder = data_path / controller.name
        controller.thumbnail_folder = data_path / 'thumbnails'
        create_paths(controller.thumbnail_folder, controller.temp_folder)
        # The Presentation plugin checks its controllers even when it is turned off. Checking PowerPoint again right
        # after it has been closed hangs OpenLP, so the application is checked only once for both plugins.
        presentations = PluginManager.get_plugin_by_name('presentations')
        other = presentations.controllers.get(controller.name) if presentations else None
        if other is not None:
            controller.check_available = other.is_available
        self.controllers[controller.name] = controller

    def check_pre_conditions(self):
        """
        Load the controllers of the Presentation plugin. The plugin can run if there are any.
        """
        # Import the controllers like the Presentation plugin does. extension_loader() is not used, because its
        # arguments differ between OpenLP versions.
        controller_dir = AppLocation.get_directory(AppLocation.PluginsDir) / 'presentations' / 'lib'
        # Find all files that do not begin with '.' (lp:#1738047) and end with controller.py
        for controller_path in controller_dir.glob('[!.]*controller.py'):
            if controller_path.name == 'presentationcontroller.py':
                continue
            try:
                importlib.import_module('openlp.plugins.presentations.lib.' + controller_path.stem)
            except (ImportError, OSError):
                log.exception('Failed to import the presentation controller {path}'.format(path=controller_path))
        controller_classes = PresentationController.__subclasses__()
        for controller_class in controller_classes:
            # Don't use classes marked as base
            if getattr(controller_class, 'base_class', False):
                controller_classes.extend(controller_class.__subclasses__())
                continue
            self.register_controller(controller_class(self))
        return bool(self.controllers)

    @staticmethod
    def about():
        """
        Return the about text for the plugin manager
        """
        about_text = translate('PresentationFolderPlugin', '<strong>Presentation Folder Plugin</strong>'
                               '<br />The presentation folder plugin shows the presentations of a folder on disk '
                               'using the presentation programs of the Presentation plugin. The folders and files on '
                               'disk are the library, so no database is used.')
        return about_text

    def set_plugin_text_strings(self):
        """
        Called to define all translatable texts of the plugin
        """
        # Name PluginList
        self.text_strings[StringContent.Name] = {
            'singular': translate('PresentationFolderPlugin', 'Presentation Folder', 'name singular'),
            'plural': translate('PresentationFolderPlugin', 'Presentation Folder', 'name plural')
        }
        # Name for MediaDockManager, SettingsManager
        self.text_strings[StringContent.VisibleName] = {
            'title': translate('PresentationFolderPlugin', 'Presentation Folder', 'container title')
        }
        # Middle Header Bar
        tooltips = {
            'load': translate('PresentationFolderPlugin', 'Copy presentations into the folder.'),
            'import': '',
            'new': '',
            'edit': '',
            'delete': translate('PresentationFolderPlugin', 'Move the selected presentations to the trash.'),
            'preview': translate('PresentationFolderPlugin', 'Preview the selected presentation.'),
            'live': translate('PresentationFolderPlugin', 'Send the selected presentation live.'),
            'service': translate('PresentationFolderPlugin', 'Add the selected presentations to the service.')
        }
        self.set_plugin_ui_text_strings(tooltips)
