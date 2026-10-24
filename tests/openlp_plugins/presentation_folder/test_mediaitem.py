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
Test the presentation folder plugin's media item
"""
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common import get_file_type_glob
from openlp.core.common.actions import ActionList
from openlp.core.common.registry import Registry
from openlp.core.display.screens import ScreenList
from openlp.core.lib import ServiceItemContext
from openlp.core.lib.serviceitem import ItemCapabilities, ServiceItem
from openlp.core.ui.icons import UiIcons
from openlp.plugins.presentation_folder.lib.mediaitem import PresentationFolderMediaItem
from openlp.plugins.presentations.lib.pdfcontroller import PdfController
from openlp.plugins.presentations.lib.presentationcontroller import PresentationDocument
from tests.utils.constants import RESOURCE_PATH


def write_image(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    image = QtGui.QImage(32, 24, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor('blue'))
    image.save(str(path), 'PNG')


class FakeDocument(PresentationDocument):
    """A document of a presentation application, which makes two slides when it is loaded"""
    def load_presentation(self):
        self.controller.loaded.append(self.file_path)
        for number in (1, 2):
            write_image(self.get_thumbnail_path(number))
        self.save_titles_and_notes(['First', 'Second'], ['', 'A note'])
        return True


class FakeController(object):
    """A presentation application controller, like Impress or PowerPoint"""
    name = 'Fake'
    display_name = 'Fake'
    supports = ['odp', 'pptx']
    also_supports = ['ppt']
    thumbnail_prefix = 'slide'

    def __init__(self, data_path):
        self.temp_folder = data_path / 'Fake'
        self.thumbnail_folder = data_path / 'thumbnails'
        self.docs = []
        self.loaded = []

    def enabled(self):
        return True

    def add_document(self, file_path):
        document = FakeDocument(self, file_path)
        self.docs.append(document)
        return document

    def remove_doc(self, doc):
        if doc in self.docs:
            self.docs.remove(doc)

    def close_presentation(self):
        pass


@pytest.fixture
def presentation_root(temp_folder):
    root = Path(temp_folder) / 'presentations'
    (root / 'Sunday').mkdir(parents=True)
    shutil.copy(RESOURCE_PATH / 'presentations' / 'pdf_test1.pdf', root / 'Sunday' / 'welcome.PDF')
    (root / 'Sunday' / 'sermon.odp').write_bytes(b'odp')
    (root / 'Sunday' / 'old.ppt').write_bytes(b'ppt')
    (root / 'notes.txt').write_text('x')
    return root


@pytest.fixture
def controllers(temp_folder, settings):
    data_path = Path(temp_folder) / 'data' / 'presentation_folder'
    pdf_controller = PdfController(MagicMock())
    pdf_controller.temp_folder = data_path / 'Pdf'
    pdf_controller.thumbnail_folder = data_path / 'thumbnails'
    return {'Fake': FakeController(data_path), 'Pdf': pdf_controller}


@pytest.fixture
def media_item(registry, settings, presentation_root, controllers, qapp):
    ActionList.shortcut_map = {}
    mocked_screen = MagicMock()
    mocked_screen.geometry.return_value = QtCore.QRect(0, 0, 1024, 768)
    mocked_app = MagicMock(**{'screens.return_value': [mocked_screen], 'primaryScreen.return_value': mocked_screen})
    ScreenList.create(mocked_app)
    registry.register('main_window', MagicMock())
    registry.register('service_manager', MagicMock(**{'get_drop_position.return_value': -1}))
    settings.setValue('presentation_folder/root folder', presentation_root)
    plugin = MagicMock()
    plugin.name = 'presentation_folder'
    plugin.get_string.return_value = {'title': 'Presentation Folder', 'tooltip': 'Tooltip'}
    item = PresentationFolderMediaItem(None, plugin, controllers)
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


def test_only_supported_presentations_are_listed(media_item, presentation_root):
    """Only the files an enabled controller supports are listed, regardless of the case of the extension"""
    assert sorted(media_item.get_file_list()) == sorted([presentation_root / 'Sunday' / 'old.ppt',
                                                         presentation_root / 'Sunday' / 'sermon.odp',
                                                         presentation_root / 'Sunday' / 'welcome.PDF'])
    assert get_file_type_glob('odp') in media_item.on_new_file_masks
    media_item.service_manager.supported_suffixes.assert_called_with(['*.odp', '*.pptx', '*.ppt', '*.pdf'])


def test_disabled_controller_hides_its_files(media_item, presentation_root):
    """When a controller is disabled, its files disappear from the library"""
    media_item.controllers['Fake'].enabled = lambda: False
    media_item.on_suffixes_changed()
    assert media_item.get_file_list() == [presentation_root / 'Sunday' / 'welcome.PDF']


def test_loading_the_library_does_not_open_presentations(media_item, controllers):
    """Presentations are not opened just to show the library"""
    assert controllers['Fake'].loaded == []
    assert not list(controllers['Pdf'].thumbnail_folder.glob('*/slide1.png'))


def test_generate_slide_data_for_presentation(media_item, presentation_root, controllers):
    """A presentation becomes a command service item with a slide per thumbnail"""
    # GIVEN: A service item and a presentation in the library
    file_path = presentation_root / 'Sunday' / 'sermon.odp'
    service_item = ServiceItem(media_item.plugin)

    # WHEN: Generating the slide data
    result = media_item.generate_slide_data(service_item, item=find_item(media_item, file_path))

    # THEN: The presentation was opened by its controller, and the slides point to the file
    assert result is True
    assert controllers['Fake'].loaded == [file_path]
    assert service_item.is_command()
    assert service_item.processor == 'Fake'
    assert service_item.title == 'sermon.odp'
    assert [slide['display_title'] for slide in service_item.slides] == ['First', 'Second']
    assert [slide['notes'] for slide in service_item.slides] == ['', 'A note']
    assert all(slide['path'] == str(file_path.parent) for slide in service_item.slides)
    assert service_item.is_capable(ItemCapabilities.ProvidesOwnDisplay)
    assert service_item.is_capable(ItemCapabilities.HasNotes)
    assert service_item.is_capable(ItemCapabilities.OnLoadUpdate)
    assert service_item.icon is not None


def test_generate_slide_data_updates_the_library_icon(media_item, presentation_root):
    """After a presentation has been opened, the library shows its first slide"""
    file_path = presentation_root / 'Sunday' / 'sermon.odp'
    tree_item = find_item(media_item, file_path)
    icon_before = tree_item.icon(0).cacheKey()

    media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item)

    assert find_item(media_item, file_path).icon(0).cacheKey() != icon_before
    assert media_item._icons[file_path][1].cacheKey() != UiIcons().presentation.cacheKey()


def test_generate_slide_data_for_pdf_in_service(media_item, presentation_root):
    """A PDF in the service is a command item of the PDF controller, the pages are rendered with it"""
    file_path = presentation_root / 'Sunday' / 'welcome.PDF'
    service_item = ServiceItem(media_item.plugin)

    result = media_item.generate_slide_data(service_item, item=find_item(media_item, file_path),
                                            context=ServiceItemContext.Service)

    assert result is True
    assert service_item.is_command()
    assert service_item.processor == 'Pdf'
    assert service_item.name == 'presentation_folder'
    assert len(service_item.slides) == 3


def test_generate_slide_data_for_pdf_live(media_item, presentation_root):
    """A PDF which goes live is shown as images, like in the Presentation plugin"""
    file_path = presentation_root / 'Sunday' / 'welcome.PDF'
    service_item = ServiceItem(media_item.plugin)

    result = media_item.generate_slide_data(service_item, item=find_item(media_item, file_path),
                                            context=ServiceItemContext.Live)

    assert result is True
    assert service_item.is_image()
    assert service_item.name == 'images'
    assert len(service_item.slides) == 3
    assert all(Path(slide['path']).is_file() for slide in service_item.slides)


def test_generate_slide_data_from_message_listener(media_item, presentation_root):
    """The message listener converts a PDF service item with the file path when it goes live"""
    file_path = presentation_root / 'Sunday' / 'welcome.PDF'
    service_item = ServiceItem(media_item.plugin)

    result = media_item.generate_slide_data(service_item, item=ServiceItem(media_item.plugin),
                                            context=ServiceItemContext.Live, file_path=file_path)

    assert result is True
    assert service_item.is_image()


def test_generate_slide_data_for_folder(media_item, presentation_root):
    """A folder cannot be turned into a service item"""
    tree_item = find_item(media_item, presentation_root / 'Sunday')
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item) is False


@patch('openlp.plugins.presentation_folder.lib.mediaitem.critical_error_message_box')
def test_generate_slide_data_missing_file(mocked_error, media_item, presentation_root):
    """A presentation which has disappeared shows an error"""
    tree_item = media_item.create_item_from_id(presentation_root / 'gone.odp')
    assert media_item.generate_slide_data(ServiceItem(media_item.plugin), item=tree_item) is False
    mocked_error.assert_called_once()


def test_on_add_click_adds_every_presentation_in_selected_folder(media_item, presentation_root):
    """Adding a folder to the service adds each presentation in it"""
    media_item.add_to_service = MagicMock()
    find_item(media_item, presentation_root / 'Sunday').setSelected(True)

    media_item.on_add_click()

    added = [call.args[0].data(0, QtCore.Qt.ItemDataRole.UserRole) for call in media_item.add_to_service.call_args_list]
    assert added == [presentation_root / 'Sunday' / 'old.ppt', presentation_root / 'Sunday' / 'sermon.odp',
                     presentation_root / 'Sunday' / 'welcome.PDF']


def test_delete_item_removes_thumbnails(media_item, presentation_root):
    """The thumbnails of a removed presentation are removed too"""
    file_path = presentation_root / 'Sunday' / 'sermon.odp'
    media_item.generate_slide_data(ServiceItem(media_item.plugin), item=find_item(media_item, file_path))
    thumbnail_folder = media_item.controllers['Fake'].add_document(file_path).get_thumbnail_folder()
    assert thumbnail_folder.is_dir()

    media_item.delete_item(file_path)

    assert not thumbnail_folder.exists()
    assert file_path not in media_item._icons


def test_service_load_fixes_thumbnails(media_item):
    """A service item from a service file gets its icon back, and its thumbnails point to the data folder"""
    # GIVEN: A service item like the core loads it from a service file
    service_item = ServiceItem(None)
    service_item.icon = None
    service_item.slides = [{'image': 'presentation_folder/thumbnails/abc/slide1.png'},
                           {'image': '/absolute/slide2.png', 'thumbnail': '/absolute/slide2.png'}]

    # WHEN: The service item is processed after loading
    with patch('openlp.plugins.presentation_folder.lib.mediaitem.AppLocation.get_data_path',
               return_value=Path('/data')):
        result = media_item.service_load(service_item)

    # THEN: Relative thumbnails are made absolute, others are left alone
    assert result is service_item
    assert service_item.icon is not None
    assert service_item.slides[0]['image'] == Path('/data/presentation_folder/thumbnails/abc/slide1.png')
    assert service_item.slides[0]['thumbnail'] == service_item.slides[0]['image']
    assert service_item.slides[1]['image'] == '/absolute/slide2.png'


def test_message_listener_uses_plugin_name(media_item):
    """The slide controller sends its messages to the name of the service item, i.e. of the plugin"""
    assert media_item.message_listener.startup in Registry().functions_list['presentation_folder_start']
    assert media_item.message_listener.next in Registry().functions_list['presentation_folder_next']
    assert 'presentations_start' not in Registry().functions_list


def test_remote_signals_follow_plugin_name(media_item):
    """The remote API finds the signals by the name of the plugin"""
    assert hasattr(media_item, 'presentation_folder_go_live')
    assert hasattr(media_item, 'presentation_folder_add_to_service')
