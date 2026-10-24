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
The media manager item of the Image Folder plugin
"""
import hashlib
import logging
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common import delete_file, get_images_filter
from openlp.core.common.applocation import AppLocation
from openlp.core.common.enum import ImageThemeMode
from openlp.core.common.i18n import UiStrings, translate
from openlp.core.common.path import create_paths
from openlp.core.common.registry import Registry
from openlp.core.lib import ServiceItemContext, build_icon, check_item_selected, create_thumb, validate_thumb
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import create_widget_action, critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole


log = logging.getLogger(__name__)


class ImageFolderMediaItem(FileSystemLibraryItem):
    """
    The media manager item for the Image Folder plugin. Lists the images of a folder on disk.
    """
    # The remote API looks these up as <plugin name>_go_live and <plugin name>_add_to_service
    image_folder_go_live = QtCore.Signal(list)
    image_folder_add_to_service = QtCore.Signal(list)
    log.info('{name} ImageFolderMediaItem loaded'.format(name=__name__))

    def __init__(self, parent, plugin):
        self.icon_path = 'images/image'
        self.image_suffixes = {'.' + bytes(image_format).decode().lower()
                               for image_format in QtGui.QImageReader.supportedImageFormats()}
        super().__init__(parent, plugin)

    @property
    def thumbnail_path(self) -> Path:
        """
        The folder of the thumbnails. The core looks for the thumbnails of the plugin in this folder when a service
        file is loaded.
        """
        return AppLocation.get_section_data_path(self.settings_section) / 'thumbnails'

    def setup_item(self):
        """
        Do some additional setup.
        """
        self.image_folder_go_live.connect(self.go_live_remote)
        self.image_folder_add_to_service.connect(self.add_to_service_remote)
        self.quick_preview_allowed = True
        self.has_search = True
        Registry().register_function('live_theme_changed', self.on_display_changed)
        Registry().register_function('slidecontroller_live_started', self.on_display_changed)
        # Allow DnD from the desktop
        self.list_view.activateDnD()

    def retranslate_ui(self):
        """
        Translate the toolbar actions
        """
        super().retranslate_ui()
        self.on_new_prompt = translate('ImagePlugin.MediaItem', 'Select Image(s)')
        self.on_new_file_masks = '{formats};;{files} (*)'.format(formats=get_images_filter(),
                                                                 files=UiStrings().AllFiles)
        self.replace_action.setText(UiStrings().ReplaceBG)
        self.replace_action.setToolTip(UiStrings().ReplaceLiveBG)
        self.replace_action_context.setText(UiStrings().ReplaceBG)
        self.replace_action_context.setToolTip(UiStrings().ReplaceLiveBG)
        self.reset_action.setText(UiStrings().ResetBG)
        self.reset_action.setToolTip(UiStrings().ResetLiveBG)
        self.reset_action_context.setText(UiStrings().ResetBG)
        self.reset_action_context.setToolTip(UiStrings().ResetLiveBG)

    def required_icons(self):
        """
        Set which icons the media manager tab should show
        """
        super().required_icons()
        self.add_to_service_item = True

    def add_custom_context_actions(self):
        """
        Add the background actions to the context menu
        """
        create_widget_action(self.list_view, separator=True)
        self.replace_action_context = create_widget_action(self.list_view, text=UiStrings().ReplaceBG,
                                                           icon=UiIcons().theme, triggers=self.on_replace_click)
        self.reset_action_context = create_widget_action(self.list_view, text=UiStrings().ResetBG,
                                                         icon=UiIcons().close, visible=False,
                                                         triggers=self.on_reset_click)

    def add_end_header_bar(self):
        """
        Add the background buttons to the end of the toolbar
        """
        self.replace_action = self.toolbar.add_toolbar_action('replace_action', icon=UiIcons().theme,
                                                              triggers=self.on_replace_click)
        self.reset_action = self.toolbar.add_toolbar_action('reset_action', icon=UiIcons().close,
                                                            visible=False, triggers=self.on_reset_click)

    def initialise(self):
        """
        Load the folder when the plugin is activated
        """
        self.list_view.setIconSize(QtCore.QSize(88, 50))
        create_paths(self.thumbnail_path)
        super().initialise()

    def is_supported_file(self, file_path: Path) -> bool:
        """
        Only list the images Qt can read

        :param file_path: The file to check
        """
        return file_path.suffix.lower() in self.image_suffixes

    def generate_thumbnail_path(self, file_path: Path) -> Path:
        """
        Return the path of the thumbnail of an image. There is no database to keep a file hash in, so the name is
        made from the path of the image.

        :param file_path: The image
        """
        name = hashlib.sha256(str(file_path).encode('utf-8')).hexdigest()
        return self.thumbnail_path / '{name}{ext}'.format(name=name, ext=file_path.suffix.lower())

    def load_item(self, file_path: Path) -> QtWidgets.QTreeWidgetItem:
        """
        Create the tree item for an image, with a thumbnail as the icon

        :param file_path: The image to create the item for
        """
        thumbnail_path = self.generate_thumbnail_path(file_path)
        if validate_thumb(file_path, thumbnail_path):
            icon = build_icon(thumbnail_path)
        else:
            size: Optional[QtCore.QSize] = None
            slide_height: Optional[int] = self.settings.value('advanced/slide max height')
            if slide_height and slide_height > 0:
                size = QtCore.QSize(-1, slide_height)
            icon = create_thumb(file_path, thumbnail_path, size=size)
        tree_item = QtWidgets.QTreeWidgetItem([file_path.name])
        tree_item.setIcon(0, icon)
        tree_item.setToolTip(0, str(file_path))
        return tree_item

    def delete_item(self, file_path: Path):
        """
        Remove the thumbnail of an image which was moved to the trash

        :param file_path: The image that was removed
        """
        delete_file(self.generate_thumbnail_path(file_path))

    def _get_tree_items(self, item) -> List[QtWidgets.QTreeWidgetItem]:
        """
        Turn whatever was passed to generate_slide_data into a list of tree items
        """
        if item is None:
            return self.list_view.selectedItems()
        if isinstance(item, QtCore.QModelIndex):
            item = self.list_view.itemFromIndex(item)
        return [item] if item else []

    def generate_slide_data(self, service_item, *, item=None, remote=False, context=ServiceItemContext.Service,
                            **kwargs):
        """
        Generate the slide data. All the selected images, and the images directly inside the selected folders, become
        the slides of one service item.

        :param service_item: The service item to be built on
        :param item: The tree item to be used, the selected items by default
        :param remote: Triggered from remote
        :param context: Why is it being generated
        :param kwargs: Consume other unused args specified by the base implementation, but not use by this one.
        """
        tree_items = [tree_item for tree_item in self._get_tree_items(item)
                      if tree_item.data(0, ItemTypeRole) in (ItemType.Folder, ItemType.File)]
        if not tree_items:
            return False
        file_paths = []
        for tree_item in tree_items:
            path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            for file_path in (self.folder_files(path) if tree_item.data(0, ItemTypeRole) == ItemType.Folder
                              else [path]):
                if file_path not in file_paths:
                    file_paths.append(file_path)
        # Don't try to display empty folders
        if not file_paths:
            return False
        missing_file_names = [str(file_path) for file_path in file_paths if not file_path.exists()]
        existing_file_paths = [file_path for file_path in file_paths if file_path.exists()]
        if not existing_file_paths:
            if not remote:
                critical_error_message_box(
                    translate('ImagePlugin.MediaItem', 'Missing Image(s)'),
                    translate('ImagePlugin.MediaItem', 'The following image(s) no longer exist: {names}'
                              ).format(names='\n'.join(missing_file_names)))
            return False
        elif missing_file_names and not remote and QtWidgets.QMessageBox.question(
                self, translate('ImagePlugin.MediaItem', 'Missing Image(s)'),
                translate('ImagePlugin.MediaItem', 'The following image(s) no longer exist: {names}\n'
                          'Do you want to add the other images anyway?'
                          ).format(names='\n'.join(missing_file_names))) == QtWidgets.QMessageBox.StandardButton.No:
            return False
        if len(tree_items) == 1:
            service_item.title = tree_items[0].text(0)
        else:
            service_item.title = str(self.plugin.name_strings['plural'])
        service_item.add_capability(ItemCapabilities.CanMaintain)
        service_item.add_capability(ItemCapabilities.CanPreview)
        service_item.add_capability(ItemCapabilities.CanLoop)
        service_item.add_capability(ItemCapabilities.CanAppend)
        service_item.add_capability(ItemCapabilities.CanEditTitle)
        service_item.add_capability(ItemCapabilities.HasThumbnails)
        service_item.add_capability(ItemCapabilities.ProvidesOwnTheme)
        # Lets service_load() set the icon again when the service is opened from a file
        service_item.add_capability(ItemCapabilities.OnLoadUpdate)
        # The core only knows the icons of its own plugins
        service_item.icon = UiIcons().picture
        if self.settings.value(self.settings_section + '/background mode') == ImageThemeMode.CustomTheme:
            service_item.theme = self.settings.value(self.settings_section + '/theme')
        else:
            # force a nonexistent theme
            service_item.theme = -1
        for file_path in existing_file_paths:
            thumbnail_path = self.generate_thumbnail_path(file_path)
            if not validate_thumb(file_path, thumbnail_path):
                create_thumb(file_path, thumbnail_path, return_icon=False)
            service_item.add_from_image(file_path, file_path.name, thumbnail_path)
        return True

    def service_load(self, item):
        """
        Set the icon of a service item that was loaded from a service file

        :param item: The service item that was loaded
        """
        item.icon = UiIcons().picture
        return item

    def on_reset_click(self):
        """
        Called to reset the Live background with the image selected.
        """
        self.reset_action.setVisible(False)
        self.reset_action_context.setVisible(False)
        self.live_controller.reload_theme()

    def on_display_changed(self, service_item=None):
        """
        Triggered by the change of theme in the slide controller.
        """
        self.reset_action.setVisible(False)
        self.reset_action_context.setVisible(False)

    def on_replace_click(self):
        """
        Called to replace Live background with the image selected.
        """
        if not check_item_selected(
                self.list_view,
                translate('ImagePlugin.MediaItem', 'You must select an image to replace the background with.')):
            return
        tree_item = self.list_view.selectedItems()[0]
        if tree_item.data(0, ItemTypeRole) != ItemType.File:
            # Only continue when an image is selected
            return
        file_path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if file_path.exists():
            self.live_controller.set_background_image(file_path)
            self.reset_action.setVisible(True)
            self.reset_action_context.setVisible(True)
        else:
            critical_error_message_box(
                UiStrings().LiveBGError,
                translate('ImagePlugin.MediaItem', 'There was a problem replacing your background, '
                          'the image file "{name}" no longer exists.').format(name=file_path))
