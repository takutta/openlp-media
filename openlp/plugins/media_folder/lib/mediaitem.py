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

import logging
from pathlib import Path
from typing import List, Optional

from PySide6 import QtCore, QtWidgets

from openlp.core.common.i18n import UiStrings, translate
from openlp.core.common.registry import Registry
from openlp.core.lib import ServiceItemContext
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import critical_error_message_box
from openlp.core.state import State
from openlp.core.ui.filesystemlibrary import FileSystemLibraryItem, ItemType, ItemTypeRole
from openlp.core.ui.icons import UiIcons
from openlp.core.ui.media import MediaType, get_supported_media_suffix


log = logging.getLogger(__name__)


class MediaFolderMediaItem(FileSystemLibraryItem):
    """
    The media manager item for the Media Folder plugin. Lists the audio and video files of a folder on disk.
    """
    media_go_live = QtCore.Signal(list)
    media_add_to_service = QtCore.Signal(list)
    log.info('{name} MediaFolderMediaItem loaded'.format(name=__name__))

    def __init__(self, parent, plugin):
        self.icon_path = 'images/image'
        self.clapperboard = UiIcons().clapperboard
        self.audio_suffixes = set()
        self.video_suffixes = set()
        super().__init__(parent, plugin)

    def retranslate_ui(self):
        """
        This method is called automatically to provide OpenLP with the opportunity to translate the ``MediaManagerItem``
        to another language.
        """
        super().retranslate_ui()
        self.on_new_prompt = translate('MediaFolderPlugin.MediaItem', 'Select Media')

    def setup_item(self):
        """
        Do some additional setup.
        """
        self.media_go_live.connect(self.go_live_remote)
        self.media_add_to_service.connect(self.add_to_service_remote)
        self.single_service_item = False
        self.has_search = True
        Registry().register_function('mediaitem_media_rebuild', self.rebuild_players)
        self.rebuild_players()
        # Allow DnD from the desktop
        self.list_view.activateDnD()

    def required_icons(self):
        """
        Set which icons the media manager tab should show
        """
        super().required_icons()
        if not State().check_preconditions('media_folder') or not State().check_preconditions('media_live'):
            self.can_preview = False
            self.can_make_live = False
            self.can_add_to_service = False

    def initialise(self):
        """
        Initialise the media item. The media players are ready by now, so the supported files are known.
        """
        self.rebuild_players()
        super().initialise()

    def rebuild_players(self):
        """
        Update the list of supported files when the media settings change.
        """
        audio, video = get_supported_media_suffix()
        # The suffixes are in the form of "*.mp3"
        self.audio_suffixes = {suffix[1:].lower() for suffix in audio if suffix}
        self.video_suffixes = {suffix[1:].lower() for suffix in video if suffix}
        self.on_new_file_masks = translate('MediaPlugin.MediaItem',
                                           'Videos ({video});;Audio ({audio});;{files} '
                                           '(*)').format(video=' '.join(video),
                                                         audio=' '.join(audio),
                                                         files=UiStrings().AllFiles)

    def is_supported_file(self, file_path: Path) -> bool:
        """
        Only list audio and video files

        :param file_path: The file to check
        """
        suffix = file_path.suffix.lower()
        return suffix in self.audio_suffixes or suffix in self.video_suffixes

    def load_item(self, file_path: Path) -> QtWidgets.QTreeWidgetItem:
        """
        Create the tree item for a media file

        :param file_path: The file to create the item for
        """
        tree_item = QtWidgets.QTreeWidgetItem([file_path.name])
        if file_path.suffix.lower() in self.audio_suffixes:
            tree_item.setIcon(0, UiIcons().audio)
        else:
            tree_item.setIcon(0, UiIcons().video)
        tree_item.setToolTip(0, str(file_path))
        return tree_item

    def _get_tree_item(self, item) -> Optional[QtWidgets.QTreeWidgetItem]:
        """
        Turn whatever was passed to generate_slide_data into a tree item
        """
        if item is None:
            return self.list_view.currentItem()
        if isinstance(item, QtCore.QModelIndex):
            return self.list_view.itemFromIndex(item)
        return item

    def generate_slide_data(self, service_item, *, item=None, remote=False, context=ServiceItemContext.Service,
                            **kwargs):
        """
        Generate the slide data.

        :param service_item: The service item to be built on
        :param item: The tree item to be used
        :param remote: Triggered from remote
        :param context: Why is it being generated
        :param kwargs: Consume other unused args specified by the base implementation, but not use by this one.
        """
        tree_item = self._get_tree_item(item)
        if tree_item is None or tree_item.data(0, ItemTypeRole) != ItemType.File:
            return False
        file_path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not file_path.exists():
            if not remote:
                critical_error_message_box(
                    translate('MediaPlugin.MediaItem', 'Missing Media File'),
                    translate('MediaPlugin.MediaItem', 'The file {name} no longer exists.').format(name=file_path))
            return False
        service_item.title = file_path.name
        service_item.processor = 'qt6'
        service_item.add_from_command(str(file_path.parent), file_path.name, self.clapperboard)
        service_item.set_media_length(self.media_controller.media_length(file_path))
        service_item.add_capability(ItemCapabilities.CanAutoStartForLive)
        service_item.add_capability(ItemCapabilities.CanEditTitle)
        service_item.add_capability(ItemCapabilities.RequiresMedia)
        # force a non-existent theme
        service_item.theme = -1
        # validate the item after all capabilities has been added
        service_item.validate_item()
        return True

    def on_add_click(self):
        """
        Add the selected files to the service. Selected folders add the media files directly inside them.
        """
        if not self.list_view.selectedIndexes():
            super().on_add_click()
            return
        drop_position = self.service_manager.get_drop_position()
        for file_path in self.selected_file_paths():
            self.add_to_service(self.create_item_from_id(file_path), position=drop_position)
            if drop_position != -1:
                drop_position += 1

    def get_list(self, media_type: MediaType = MediaType.Audio) -> List[Path]:
        """
        Get the list of media, optionally of only one type.

        :param media_type: Type to get, defaults to audio.
        :return: The media list
        """
        suffixes = self.audio_suffixes if media_type == MediaType.Audio else self.video_suffixes
        return [path for path in self.get_file_list() if path.suffix.lower() in suffixes]
