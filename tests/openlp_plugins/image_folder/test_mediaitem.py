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
Test the image folder plugin's media item
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common.actions import ActionList
from openlp.core.common.enum import ImageThemeMode
from openlp.core.lib.serviceitem import ItemCapabilities, ServiceItem
from openlp.plugins.image_folder.lib.mediaitem import ImageFolderMediaItem


def write_image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QtGui.QImage(32, 16, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor('red'))
    assert image.save(str(path), 'PNG')


@pytest.fixture
def image_root(temp_folder):
    root = Path(temp_folder) / 'images'
    write_image(root / 'b 10.png')
    write_image(root / 'b 2.PNG')
    write_image(root / 'Easter' / 'cross.png')
    write_image(root / 'Easter' / 'tomb.png')
    (root / 'Easter' / 'Empty').mkdir()
    (root / 'notes.txt').write_text('x')
    return root


@pytest.fixture
def data_path(temp_folder):
    data_path = Path(temp_folder) / 'data'
    with patch('openlp.plugins.image_folder.lib.mediaitem.AppLocation.get_section_data_path',
               side_effect=lambda section: data_path / section):
        yield data_path


@pytest.fixture
def media_item(registry, settings, image_root, data_path):
    ActionList.shortcut_map = {}
    registry.register('main_window', MagicMock())
    registry.register('service_manager', MagicMock(**{'get_drop_position.return_value': -1}))
    registry.register('live_controller', MagicMock())
    settings.extend_default_settings({'image_folder/background mode': ImageThemeMode.Black,
                                      'image_folder/theme': None})
    settings.setValue('image_folder/root folder', image_root)
    plugin = MagicMock()
    plugin.name = 'image_folder'
    plugin.name_strings = {'singular': 'Image Folder', 'plural': 'Images'}
    plugin.get_string.return_value = {'title': 'Image Folder', 'tooltip': 'Tooltip'}
    item = ImageFolderMediaItem(None, plugin)
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


def test_only_images_are_listed(media_item, image_root):
    """Only images are listed, regardless of the case of the extension"""
    assert sorted(media_item.get_file_list()) == sorted([image_root / 'b 2.PNG', image_root / 'b 10.png',
                                                         image_root / 'Easter' / 'cross.png',
                                                         image_root / 'Easter' / 'tomb.png'])


def test_thumbnails_are_created(media_item, image_root, data_path):
    """Loading the library creates a thumbnail for each image in the data folder of the plugin"""
    thumbnail_path = media_item.generate_thumbnail_path(image_root / 'b 2.PNG')
    assert thumbnail_path.parent == data_path / 'image_folder' / 'thumbnails'
    assert thumbnail_path.suffix == '.png'
    assert thumbnail_path.exists()
    assert not find_item(media_item, image_root / 'b 2.PNG').icon(0).isNull()


def test_delete_item_removes_thumbnail(media_item, image_root):
    """The thumbnail of a removed image is removed too"""
    thumbnail_path = media_item.generate_thumbnail_path(image_root / 'b 2.PNG')
    media_item.delete_item(image_root / 'b 2.PNG')
    assert not thumbnail_path.exists()


def test_generate_slide_data_for_one_image(media_item, image_root):
    """One image becomes a service item with one slide"""
    # GIVEN: A service item and an image in the library
    service_item = ServiceItem(media_item.plugin)

    # WHEN: Generating the slide data for the image
    result = media_item.generate_slide_data(service_item, item=find_item(media_item, image_root / 'b 2.PNG'))

    # THEN: The service item shows the image
    assert result is True
    assert service_item.title == 'b 2.PNG'
    assert service_item.is_image()
    assert [slide['path'] for slide in service_item.slides] == [image_root / 'b 2.PNG']
    assert service_item.slides[0]['thumbnail'] == media_item.generate_thumbnail_path(image_root / 'b 2.PNG')
    assert service_item.is_capable(ItemCapabilities.CanLoop)
    assert service_item.is_capable(ItemCapabilities.OnLoadUpdate)
    assert service_item.icon is not None
    assert service_item.theme == -1


def test_generate_slide_data_for_folder(media_item, image_root):
    """A folder becomes one service item with the images directly inside it"""
    service_item = ServiceItem(media_item.plugin)

    result = media_item.generate_slide_data(service_item, item=find_item(media_item, image_root / 'Easter'))

    assert result is True
    assert service_item.title == 'Easter'
    assert [slide['path'] for slide in service_item.slides] == [image_root / 'Easter' / 'cross.png',
                                                                image_root / 'Easter' / 'tomb.png']


def test_generate_slide_data_for_empty_folder(media_item, image_root):
    """An empty folder cannot be shown"""
    tree_item = find_item(media_item, image_root / 'Easter' / 'Empty')
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item) is False


def test_generate_slide_data_for_selection(media_item, image_root):
    """The selected images and folders become one service item, without duplicates"""
    # GIVEN: A selected folder, an image inside it and another image
    find_item(media_item, image_root / 'Easter').setSelected(True)
    find_item(media_item, image_root / 'Easter' / 'tomb.png').setSelected(True)
    find_item(media_item, image_root / 'b 10.png').setSelected(True)
    service_item = ServiceItem(media_item.plugin)

    # WHEN: Generating the slide data from the selection
    result = media_item.generate_slide_data(service_item)

    # THEN: Every image is added once, and the title is the plural name of the plugin
    assert result is True
    assert service_item.title == 'Images'
    assert sorted(slide['path'] for slide in service_item.slides) == sorted([image_root / 'Easter' / 'cross.png',
                                                                            image_root / 'Easter' / 'tomb.png',
                                                                            image_root / 'b 10.png'])


def test_generate_slide_data_custom_theme(media_item, image_root, settings):
    """The theme of the images comes from the settings of the plugin"""
    settings.setValue('image_folder/background mode', ImageThemeMode.CustomTheme)
    settings.setValue('image_folder/theme', 'Pictures')
    service_item = ServiceItem(media_item.plugin)

    media_item.generate_slide_data(service_item, item=find_item(media_item, image_root / 'b 2.PNG'))

    assert service_item.theme == 'Pictures'


@patch('openlp.plugins.image_folder.lib.mediaitem.critical_error_message_box')
def test_generate_slide_data_missing_image(mocked_error, media_item, image_root):
    """An image which has disappeared shows an error"""
    tree_item = media_item.create_item_from_id(image_root / 'gone.png')
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item) is False
    mocked_error.assert_called_once()


def test_generate_slide_data_from_remote(media_item, image_root):
    """The remote API can show an image of the library by its path, but nothing outside the library"""
    tree_item = media_item.create_item_from_id(str(image_root / 'b 10.png'))
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item, remote=True) is True
    outside = media_item.create_item_from_id(str(image_root.parent / 'outside.png'))
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=outside, remote=True) is False


def test_service_load_sets_icon(media_item):
    """A service item loaded from a service file gets its icon back"""
    service_item = ServiceItem(None)
    service_item.icon = None

    assert media_item.service_load(service_item) is service_item
    assert service_item.icon is not None


def test_replace_background(media_item, image_root):
    """The selected image replaces the background of the live display"""
    # GIVEN: A selected image
    find_item(media_item, image_root / 'b 10.png').setSelected(True)

    # WHEN: Replace background is clicked
    media_item.on_replace_click()

    # THEN: The live display uses the image, and the background can be reset
    media_item.live_controller.set_background_image.assert_called_once_with(image_root / 'b 10.png')
    assert media_item.reset_action.isVisible()
    media_item.on_reset_click()
    media_item.live_controller.reload_theme.assert_called_once()


def test_replace_background_with_folder(media_item, image_root):
    """A folder cannot replace the background"""
    find_item(media_item, image_root / 'Easter').setSelected(True)
    media_item.on_replace_click()
    media_item.live_controller.set_background_image.assert_not_called()


def test_remote_signals_follow_plugin_name(media_item):
    """The remote API finds the signals by the name of the plugin"""
    assert hasattr(media_item, 'image_folder_go_live')
    assert hasattr(media_item, 'image_folder_add_to_service')
