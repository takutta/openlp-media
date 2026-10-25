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
Test the media folder plugin's media item
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openlp.core.common.actions import ActionList
from openlp.core.lib.serviceitem import ItemCapabilities, ServiceItem
from openlp.core.state import State
from openlp.core.ui.media import MediaType
from openlp.plugins.media_folder.lib.mediaitem import MediaFolderMediaItem
from openlp.plugins.filesystem_library.compat import QtCore, QtWidgets


SUFFIXES = (['', '*.mp3', '*.ogg'], ['', '*.mp4', '*.MKV'])


@pytest.fixture
def media_root(temp_folder):
    root = Path(temp_folder) / 'media'
    (root / 'Worship').mkdir(parents=True)
    (root / 'song.mp3').write_bytes(b'')
    (root / 'Worship' / 'intro.mp4').write_bytes(b'')
    (root / 'Worship' / 'loop.MKV').write_bytes(b'')
    (root / 'notes.txt').write_bytes(b'')
    (root / 'README').write_bytes(b'')
    return root


@pytest.fixture
def media_item(registry, settings, state, media_root):
    ActionList.shortcut_map = {}
    State().add_service('mediacontroller', 0)
    State().update_pre_conditions('mediacontroller', True)
    State().add_service('media_live', 0)
    State().update_pre_conditions('media_live', True)
    State().add_service('media_folder', 0, requires='mediacontroller')
    State().flush_preconditions()
    registry.register('main_window', MagicMock())
    registry.register('service_manager', MagicMock(**{'get_drop_position.return_value': -1}))
    registry.register('media_controller', MagicMock(**{'media_length.return_value': 1234}))
    settings.setValue('media_folder/root folder', media_root)
    plugin = MagicMock()
    plugin.name = 'media_folder'
    plugin.get_string.return_value = {'title': 'Media Folder', 'tooltip': 'Tooltip'}
    with patch('openlp.plugins.media_folder.lib.mediaitem.get_supported_media_suffix', return_value=SUFFIXES):
        item = MediaFolderMediaItem(None, plugin)
        item.initialise()
    yield item
    item._reload_timer.stop()
    ActionList.shortcut_map = {}


def find_item(media_item, path):
    iterator = QtWidgets.QTreeWidgetItemIterator(media_item.list_view)
    while iterator.value():
        if iterator.value().data(0, QtCore.Qt.ItemDataRole.UserRole) == path:
            return iterator.value()
        iterator += 1
    return None


def test_only_media_files_are_listed(media_item, media_root):
    """Only audio and video files are listed, regardless of the case of the extension"""
    assert sorted(media_item.get_file_list()) == sorted([media_root / 'song.mp3',
                                                         media_root / 'Worship' / 'intro.mp4',
                                                         media_root / 'Worship' / 'loop.MKV'])


def test_get_list(media_item, media_root):
    """get_list() filters by media type"""
    assert media_item.get_list(MediaType.Audio) == [media_root / 'song.mp3']
    assert sorted(media_item.get_list(MediaType.Video)) == sorted([media_root / 'Worship' / 'intro.mp4',
                                                                   media_root / 'Worship' / 'loop.MKV'])


def test_generate_slide_data(media_item, media_root):
    """A service item is built straight from the file path"""
    # GIVEN: A service item and a media file in the library
    service_item = ServiceItem(media_item.plugin)
    tree_item = find_item(media_item, media_root / 'Worship' / 'intro.mp4')

    # WHEN: Generating the slide data
    result = media_item.generate_slide_data(service_item, item=tree_item)

    # THEN: The service item points to the file
    assert result is True
    assert service_item.title == 'intro.mp4'
    assert service_item.processor == 'qt6'
    assert service_item.slides[0]['path'] == str(media_root / 'Worship')
    assert service_item.slides[0]['title'] == 'intro.mp4'
    assert service_item.is_capable(ItemCapabilities.RequiresMedia)
    assert service_item.media_length == 1234
    assert service_item.is_capable(ItemCapabilities.OnLoadUpdate)
    assert service_item.icon is not None


def test_service_load_sets_icon(media_item):
    """A service item loaded from a service file gets its icon back"""
    # GIVEN: A service item without an icon, like the core makes for plugins it does not know
    service_item = ServiceItem(None)
    service_item.icon = None

    # WHEN: The service item is processed after loading
    result = media_item.service_load(service_item)

    # THEN: The same item is returned with an icon
    assert result is service_item
    assert service_item.icon is not None


def test_generate_slide_data_for_folder(media_item, media_root):
    """A folder cannot be turned into a service item"""
    assert media_item.generate_slide_data(ServiceItem(None), item=find_item(media_item, media_root / 'Worship')) \
        is False


@patch('openlp.plugins.media_folder.lib.mediaitem.critical_error_message_box')
def test_generate_slide_data_missing_file(mocked_error, media_item, media_root):
    """A file which has disappeared shows an error"""
    tree_item = media_item.create_item_from_id(media_root / 'gone.mp3')
    assert media_item.generate_slide_data(ServiceItem(None), item=tree_item) is False
    mocked_error.assert_called_once()


def test_on_add_click_adds_every_file_in_selected_folder(media_item, media_root):
    """Adding a folder to the service adds each media file in it"""
    # GIVEN: A selected folder
    media_item.add_to_service = MagicMock()
    find_item(media_item, media_root / 'Worship').setSelected(True)

    # WHEN: Add to service is clicked
    media_item.on_add_click()

    # THEN: Both files are added
    added = [call.args[0].data(0, QtCore.Qt.ItemDataRole.UserRole) for call in media_item.add_to_service.call_args_list]
    assert added == [media_root / 'Worship' / 'intro.mp4', media_root / 'Worship' / 'loop.MKV']


def test_remote_signals_follow_plugin_name(media_item):
    """The remote API finds the signals by the name of the plugin"""
    assert hasattr(media_item, 'media_folder_go_live')
    assert hasattr(media_item, 'media_folder_add_to_service')
