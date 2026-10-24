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
The media manager item of the Presentation Folder plugin
"""
import logging
import os
from pathlib import Path
from typing import Dict, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common import get_file_type_glob
from openlp.core.common.applocation import AppLocation
from openlp.core.common.i18n import translate
from openlp.core.common.registry import Registry
from openlp.core.lib import ServiceItemContext, build_icon, create_thumb, validate_thumb
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import create_horizontal_adjusting_combo_box, critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole
from openlp.plugins.presentation_folder.lib.messagelistener import FolderMessageListener
from openlp.plugins.presentations.lib.mediaitem import PresentationMediaItem
from openlp.plugins.presentations.lib.pdfcontroller import PDF_CONTROLLER_FILETYPES


log = logging.getLogger(__name__)


class PresentationFolderMediaItem(FileSystemLibraryItem):
    """
    The media manager item for the Presentation Folder plugin. Lists the presentations of a folder on disk which the
    enabled presentation controllers support.
    """
    # The remote API looks these up as <plugin name>_go_live and <plugin name>_add_to_service
    presentation_folder_go_live = QtCore.Signal(list)
    presentation_folder_add_to_service = QtCore.Signal(list)
    log.info('{name} PresentationFolderMediaItem loaded'.format(name=__name__))

    # These do not use the database, so they are shared with the Presentation plugin
    find_controller_by_type = PresentationMediaItem.find_controller_by_type
    populate_display_types = PresentationMediaItem.populate_display_types
    clean_up_thumbnails = PresentationMediaItem.clean_up_thumbnails

    def __init__(self, parent, plugin, controllers):
        self.icon_path = 'presentations/presentation'
        self.controllers = controllers
        self.on_new_file_masks = ''
        self.suffixes = set()
        # Library icons by file path, with the modification time of the file they were made for
        self._icons: Dict[Path, Tuple[float, QtGui.QIcon]] = {}
        super().__init__(parent, plugin)

    def retranslate_ui(self):
        """
        Translate the user interface
        """
        super().retranslate_ui()
        self.on_new_prompt = translate('PresentationPlugin.MediaItem', 'Select Presentation(s)')
        self.automatic = translate('PresentationPlugin.MediaItem', 'Automatic')
        self.display_type_label.setText(translate('PresentationPlugin.MediaItem', 'Present using:'))

    def setup_item(self):
        """
        Do some additional setup.
        """
        self.presentation_folder_go_live.connect(self.go_live_remote)
        self.presentation_folder_add_to_service.connect(self.add_to_service_remote)
        self.message_listener = FolderMessageListener(self)
        self.has_search = True
        self.single_service_item = False
        Registry().register_function('mediaitem_presentation_rebuild', self.populate_display_types)
        Registry().register_function('mediaitem_suffixes', self.on_suffixes_changed)
        # Allow DnD from the desktop
        self.list_view.activateDnD()

    def add_middle_header_bar(self):
        """
        Add the "Present using" selection after the folder buttons
        """
        super().add_middle_header_bar()
        self.presentation_widget = QtWidgets.QWidget(self)
        self.presentation_widget.setObjectName('presentation_widget')
        self.display_layout = QtWidgets.QFormLayout(self.presentation_widget)
        self.display_layout.setContentsMargins(self.display_layout.spacing(), self.display_layout.spacing(),
                                               self.display_layout.spacing(), self.display_layout.spacing())
        self.display_layout.setObjectName('display_layout')
        self.display_type_label = QtWidgets.QLabel(self.presentation_widget)
        self.display_type_label.setObjectName('display_type_label')
        self.display_type_combo_box = create_horizontal_adjusting_combo_box(self.presentation_widget,
                                                                            'display_type_combo_box')
        self.display_type_label.setBuddy(self.display_type_combo_box)
        self.display_layout.addRow(self.display_type_label, self.display_type_combo_box)
        self.page_layout.addWidget(self.presentation_widget)

    def initialise(self):
        """
        Load the folder when the plugin is activated
        """
        self.list_view.setIconSize(QtCore.QSize(88, 50))
        self.populate_display_types()
        self.build_file_mask_string()
        super().initialise()

    def build_file_mask_string(self):
        """
        Collect the file types of the enabled controllers, for the library and the Open file dialog
        """
        file_types = []
        for controller in self.controllers.values():
            if controller.enabled():
                for file_type in controller.supports + controller.also_supports:
                    if file_type not in file_types:
                        file_types.append(file_type)
        self.suffixes = {'.' + file_type.lower() for file_type in file_types}
        self.service_manager.supported_suffixes(['*.' + file_type for file_type in file_types])
        file_type_string = ' '.join(get_file_type_glob(file_type) for file_type in file_types)
        self.on_new_file_masks = translate('PresentationPlugin.MediaItem',
                                           'Presentations ({text})').format(text=file_type_string)

    def on_suffixes_changed(self):
        """
        The enabled controllers have changed, so the library might show different files
        """
        self.build_file_mask_string()
        self.reload()

    def is_supported_file(self, file_path: Path) -> bool:
        """
        Only list the files an enabled controller supports

        :param file_path: The file to check
        """
        return file_path.suffix.lower() in self.suffixes

    def _get_icon(self, file_path: Path) -> QtGui.QIcon:
        """
        Return the icon for a presentation in the library: a thumbnail of the first slide when the presentation has
        been shown before, the presentation icon otherwise. Opening presentations to make thumbnails would be too slow
        for a whole folder, so it is only done when a presentation is used.

        :param file_path: The presentation
        """
        try:
            modified = file_path.stat().st_mtime
        except OSError:
            return UiIcons().delete
        cached = self._icons.get(file_path)
        if cached and cached[0] == modified:
            return cached[1]
        icon = UiIcons().presentation
        controller_name = self.find_controller_by_type(file_path)
        if controller_name:
            doc = self.controllers[controller_name].add_document(file_path)
            preview_path = doc.get_thumbnail_path(1, True)
            if preview_path:
                thumbnail_path = doc.get_thumbnail_folder() / 'icon.png'
                if validate_thumb(preview_path, thumbnail_path):
                    icon = build_icon(thumbnail_path)
                else:
                    icon = create_thumb(preview_path, thumbnail_path)
            doc.close_presentation()
        self._icons[file_path] = (modified, icon)
        return icon

    def _update_icon(self, file_path: Path):
        """
        Show the new thumbnail of a presentation which was just opened

        :param file_path: The presentation
        """
        self._icons.pop(file_path, None)
        iterator = QtWidgets.QTreeWidgetItemIterator(self.list_view)
        while iterator.value():
            tree_item = iterator.value()
            if tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole) == file_path:
                tree_item.setIcon(0, self._get_icon(file_path))
            iterator += 1

    def load_item(self, file_path: Path) -> QtWidgets.QTreeWidgetItem:
        """
        Create the tree item for a presentation

        :param file_path: The presentation to create the item for
        """
        tree_item = QtWidgets.QTreeWidgetItem([file_path.name])
        tree_item.setIcon(0, self._get_icon(file_path))
        tree_item.setToolTip(0, str(file_path))
        return tree_item

    def delete_item(self, file_path: Path):
        """
        Remove the thumbnails of a presentation which is being moved to the trash

        :param file_path: The presentation that is being removed
        """
        self._icons.pop(file_path, None)
        self.clean_up_thumbnails(file_path)

    def _show_error(self, remote: bool, message: str, file_path: Path):
        if not remote:
            critical_error_message_box(translate('PresentationPlugin.MediaItem', 'Missing Presentation'),
                                       message.format(name=file_path))

    def generate_slide_data(self, service_item, *, item=None, remote=False, context=ServiceItemContext.Service,
                            file_path=None, **kwargs):
        """
        Generate the slide data. PDF files and the like are shown as images when they go live or are previewed,
        everything else is shown by its presentation application.

        :param service_item: The service item to be built on
        :param item: The tree item to be used. The message listener passes a service item together with file_path.
        :param remote: Triggered from remote
        :param context: Why is it being generated
        :param file_path: The presentation, instead of the one in the item
        :param kwargs: Consume other unused args specified by the base implementation, but not use by this one.
        """
        if file_path is None:
            tree_item = self._get_tree_item(item)
            if tree_item is None or tree_item.data(0, ItemTypeRole) != ItemType.File:
                return False
            file_path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not self.display_type_combo_box.currentText():
            return False
        if not file_path.exists():
            self._show_error(remote, translate('PresentationPlugin.MediaItem',
                                               'The presentation {name} no longer exists.'), file_path)
            return False
        if not os.access(file_path, os.R_OK):
            self._show_error(remote, translate('PresentationPlugin.MediaItem',
                                               'The presentation {name} is inaccessible.'), file_path)
            return False
        service_item.title = file_path.name
        service_item.add_capability(ItemCapabilities.CanEditTitle)
        if file_path.suffix.lower()[1:] in PDF_CONTROLLER_FILETYPES and context != ServiceItemContext.Service:
            result = self._generate_image_slides(service_item, file_path)
        else:
            result = self._generate_command_slides(service_item, file_path, remote)
        if result:
            self._update_icon(file_path)
        return result

    def _generate_image_slides(self, service_item, file_path: Path) -> bool:
        """
        Turn the pages of a PDF file (or the like) into the image slides of a service item

        :param service_item: The service item to be built on
        :param file_path: The presentation
        """
        processor = self.find_controller_by_type(file_path)
        if not processor:
            return False
        service_item.add_capability(ItemCapabilities.CanMaintain)
        service_item.add_capability(ItemCapabilities.CanPreview)
        service_item.add_capability(ItemCapabilities.CanLoop)
        service_item.add_capability(ItemCapabilities.CanAppend)
        service_item.add_capability(ItemCapabilities.ProvidesOwnTheme)
        # Like the Presentation plugin, show the pages with the image presentation code
        service_item.name = 'images'
        # force a nonexistent theme
        service_item.theme = -1
        service_item.processor = None
        doc = self.controllers[processor].add_document(file_path)
        if doc.get_thumbnail_path(1, True) is None or not (doc.get_temp_folder() / 'mainslide001.png').is_file():
            doc.load_presentation()
        number = 1
        image_path = doc.get_temp_folder() / 'mainslide{number:0>3d}.png'.format(number=number)
        while image_path.is_file():
            thumbnail_path = doc.get_thumbnail_folder() / 'slide{number:d}.png'.format(number=number)
            service_item.add_from_image(image_path, file_path.name, thumbnail=thumbnail_path)
            number += 1
            image_path = doc.get_temp_folder() / 'mainslide{number:0>3d}.png'.format(number=number)
        service_item.add_capability(ItemCapabilities.HasThumbnails)
        doc.close_presentation()
        service_item.validate_item()
        return True

    def _generate_command_slides(self, service_item, file_path: Path, remote: bool) -> bool:
        """
        Make a service item which lets a presentation application show the presentation

        :param service_item: The service item to be built on
        :param file_path: The presentation
        :param remote: Triggered from remote
        """
        service_item.processor = self.display_type_combo_box.currentText()
        if self.display_type_combo_box.itemData(self.display_type_combo_box.currentIndex()) == 'automatic':
            service_item.processor = self.find_controller_by_type(file_path)
            if not service_item.processor:
                return False
        service_item.add_capability(ItemCapabilities.ProvidesOwnDisplay)
        doc = self.controllers[service_item.processor].add_document(file_path)
        if doc.get_thumbnail_path(1, True) is None:
            doc.load_presentation()
        if not doc.get_thumbnail_path(1, True):
            doc.close_presentation()
            self._show_error(remote, translate('PresentationPlugin.MediaItem',
                                               'The presentation {name} is incomplete, please reload.'), file_path)
            return False
        titles, notes = doc.get_titles_and_notes()
        service_item.add_capability(ItemCapabilities.HasDisplayTitle)
        if notes.count('') != len(notes):
            service_item.add_capability(ItemCapabilities.HasNotes)
        service_item.add_capability(ItemCapabilities.HasThumbnails)
        # Lets service_load() fix the thumbnails and the icon when the service is opened from a file
        service_item.add_capability(ItemCapabilities.OnLoadUpdate)
        # The core only knows the icons of its own plugins
        service_item.icon = UiIcons().presentation
        number = 1
        thumbnail_path = doc.get_thumbnail_path(number, True)
        while thumbnail_path:
            title = titles[number - 1] if titles and len(titles) >= number else ''
            note = notes[number - 1] if notes and len(notes) >= number else ''
            service_item.add_from_command(str(file_path.parent), file_path.name, thumbnail_path, title, note,
                                          doc.get_sha256_file_hash())
            number += 1
            thumbnail_path = doc.get_thumbnail_path(number, True)
        doc.close_presentation()
        service_item.validate_item()
        return True

    def service_load(self, item):
        """
        Fix a service item that was loaded from a service file. The core sets the icon and the thumbnail paths only for
        the items of the Presentation plugin, so this does the same for this plugin.

        :param item: The service item that was loaded
        """
        item.icon = UiIcons().presentation
        data_path = AppLocation.get_data_path()
        for slide in item.slides:
            image = slide.get('image')
            # Service files keep the thumbnails relative to the data folder
            if image and not isinstance(image, QtGui.QIcon) and not Path(image).is_absolute():
                slide['image'] = slide['thumbnail'] = data_path / image
        return item
