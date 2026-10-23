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
Test the FileSystemLibraryItem class
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6 import QtCore, QtWidgets

from openlp.core.common.actions import ActionList
from openlp.core.ui.filesystemlibrary import FileSystemLibraryItem, ItemType, ItemTypeRole


class TextLibraryItem(FileSystemLibraryItem):
    """A library item which lists text files"""
    def is_supported_file(self, file_path):
        return file_path.suffix.lower() == '.txt'


@pytest.fixture(autouse=True)
def clean_shortcut_map():
    """The shortcut map is shared between all actions, so clear it between tests"""
    ActionList.shortcut_map = {}
    yield
    ActionList.shortcut_map = {}


def make_plugin(name='test_library'):
    plugin = MagicMock()
    plugin.name = name
    plugin.get_string.return_value = {'title': 'Title', 'tooltip': 'Tooltip'}
    return plugin


@pytest.fixture
def root(temp_folder):
    root = Path(temp_folder) / 'library'
    (root / 'Sub B').mkdir(parents=True)
    (root / 'Sub A' / 'Deep').mkdir(parents=True)
    (root / '.hidden').mkdir()
    (root / 'song 10.txt').write_text('x')
    (root / 'song 2.txt').write_text('x')
    (root / 'ignored.jpg').write_text('x')
    (root / 'Sub A' / 'a.txt').write_text('x')
    (root / 'Sub A' / 'Deep' / 'deep.txt').write_text('x')
    (root / '.hidden' / 'hidden.txt').write_text('x')
    return root


@pytest.fixture
def library_item(registry, settings, root):
    registry.register('main_window', MagicMock())
    settings.setValue('test_library/root folder', root)
    item = TextLibraryItem(None, make_plugin())
    item.initialise()
    yield item
    item._reload_timer.stop()


def top_level_texts(library_item):
    return [library_item.list_view.topLevelItem(i).text(0) for i in range(library_item.list_view.topLevelItemCount())]


def find_item(library_item, path):
    iterator = QtWidgets.QTreeWidgetItemIterator(library_item.list_view)
    while iterator.value():
        if iterator.value().data(0, QtCore.Qt.ItemDataRole.UserRole) == path:
            return iterator.value()
        iterator += 1
    return None


def test_reload_lists_folders_then_files(library_item):
    """Folders come first, files are naturally sorted, and hidden and unsupported files are skipped"""
    # GIVEN: A library item with a root folder (loaded by the fixture)
    # THEN: The tree reflects the folder on disk
    assert top_level_texts(library_item) == ['Sub A', 'Sub B', 'song 2.txt', 'song 10.txt']
    sub_a = library_item.list_view.topLevelItem(0)
    assert sub_a.data(0, ItemTypeRole) == ItemType.Folder
    assert [sub_a.child(i).text(0) for i in range(sub_a.childCount())] == ['Deep', 'a.txt']


def test_get_file_list_and_search(library_item, root):
    """All supported files are found recursively and can be searched by name"""
    # WHEN: Getting the file list and searching
    files = library_item.get_file_list()
    result = library_item.search('DEEP', False)

    # THEN: The right files are returned
    assert sorted(files) == sorted([root / 'song 10.txt', root / 'song 2.txt', root / 'Sub A' / 'a.txt',
                                    root / 'Sub A' / 'Deep' / 'deep.txt'])
    assert result == [[str(root / 'Sub A' / 'Deep' / 'deep.txt'), 'deep.txt']]


def test_no_root_shows_placeholder(registry, settings):
    """Without a root folder a disabled placeholder is shown"""
    # GIVEN: A library item without a root folder
    registry.register('main_window', MagicMock())
    item = TextLibraryItem(None, make_plugin())

    # WHEN: The item is initialised
    item.initialise()

    # THEN: There is one disabled item and no files
    assert item.list_view.topLevelItemCount() == 1
    assert item.list_view.topLevelItem(0).flags() == QtCore.Qt.ItemFlag.NoItemFlags
    assert item.get_file_list() == []
    assert item.root_path is None


def test_reload_keeps_expanded_folders(library_item, root):
    """Expanded folders stay expanded after a reload"""
    # GIVEN: An expanded folder
    find_item(library_item, root / 'Sub A').setExpanded(True)

    # WHEN: The library is reloaded
    library_item.reload()

    # THEN: The folder is still expanded
    assert find_item(library_item, root / 'Sub A').isExpanded() is True
    assert find_item(library_item, root / 'Sub B').isExpanded() is False


def test_current_folder(library_item, root):
    """The current folder is the selected folder, the folder of the selected file or the root"""
    assert library_item.current_folder == root
    find_item(library_item, root / 'Sub A' / 'a.txt').setSelected(True)
    assert library_item.current_folder == root / 'Sub A'
    library_item.list_view.clearSelection()
    find_item(library_item, root / 'Sub B').setSelected(True)
    assert library_item.current_folder == root / 'Sub B'


def test_validate_and_load_copies_files(library_item, root, temp_folder):
    """Files from outside the library are copied into the target folder"""
    # GIVEN: A file outside the library
    outside = Path(temp_folder) / 'new.txt'
    outside.write_text('new')
    target = find_item(library_item, root / 'Sub B')

    # WHEN: The file is dropped on a folder
    library_item.validate_and_load([outside], target)

    # THEN: The file is copied and shown
    assert (root / 'Sub B' / 'new.txt').read_text() == 'new'
    assert outside.exists()
    assert find_item(library_item, root / 'Sub B' / 'new.txt').isSelected()


@patch('openlp.core.ui.filesystemlibrary.critical_error_message_box')
def test_validate_and_load_skips_existing(mocked_error, library_item, root, temp_folder):
    """Files are never overwritten"""
    # GIVEN: A file with the same name as a file in the library
    outside = Path(temp_folder) / 'song 2.txt'
    outside.write_text('other')

    # WHEN: The file is added to the root
    library_item.validate_and_load([outside])

    # THEN: The existing file is untouched and the user is told
    assert (root / 'song 2.txt').read_text() == 'x'
    mocked_error.assert_called_once()


def test_dnd_move_internal(library_item, root):
    """Moving items inside the library moves the files on disk"""
    # GIVEN: A selected file
    find_item(library_item, root / 'song 2.txt').setSelected(True)

    # WHEN: It is dropped on a folder
    library_item.dnd_move_internal(find_item(library_item, root / 'Sub B'))

    # THEN: The file has moved
    assert not (root / 'song 2.txt').exists()
    assert (root / 'Sub B' / 'song 2.txt').exists()


def test_dnd_move_folder_into_itself_is_ignored(library_item, root):
    """A folder cannot be moved inside itself"""
    find_item(library_item, root / 'Sub A').setSelected(True)
    library_item.dnd_move_internal(find_item(library_item, root / 'Sub A' / 'Deep'))
    assert (root / 'Sub A' / 'Deep').is_dir()


@patch('openlp.core.ui.filesystemlibrary.move_to_trash')
@patch('openlp.core.ui.filesystemlibrary.QtWidgets.QMessageBox.question')
def test_delete_moves_to_trash(mocked_question, mocked_trash, library_item, root):
    """Deleting asks first and moves the files to the trash"""
    # GIVEN: A selected folder and a user who says yes
    mocked_question.return_value = QtWidgets.QMessageBox.StandardButton.Yes
    mocked_trash.return_value = True
    library_item.delete_item = MagicMock()
    find_item(library_item, root / 'Sub A').setSelected(True)

    # WHEN: Delete is clicked
    library_item.on_delete_click()

    # THEN: The folder is trashed and the files in it are cleaned up
    mocked_trash.assert_called_once_with(root / 'Sub A')
    assert sorted(call.args[0] for call in library_item.delete_item.call_args_list) == \
        sorted([root / 'Sub A' / 'a.txt', root / 'Sub A' / 'Deep' / 'deep.txt'])


@patch('openlp.core.ui.filesystemlibrary.move_to_trash')
@patch('openlp.core.ui.filesystemlibrary.QtWidgets.QMessageBox.question')
def test_delete_cancelled(mocked_question, mocked_trash, library_item, root):
    """Nothing is deleted when the user says no"""
    mocked_question.return_value = QtWidgets.QMessageBox.StandardButton.No
    find_item(library_item, root / 'song 2.txt').setSelected(True)
    library_item.on_delete_click()
    mocked_trash.assert_not_called()


@patch('openlp.core.ui.filesystemlibrary.QtWidgets.QInputDialog.getText')
def test_add_folder(mocked_get_text, library_item, root):
    """A new folder is created inside the current folder"""
    # GIVEN: A selected folder
    mocked_get_text.return_value = ('New', True)
    find_item(library_item, root / 'Sub B').setSelected(True)

    # WHEN: Add folder is clicked
    library_item.on_add_folder_click()

    # THEN: The folder exists and is shown
    assert (root / 'Sub B' / 'New').is_dir()
    assert find_item(library_item, root / 'Sub B' / 'New') is not None


def test_selected_file_paths_expands_folders(library_item, root):
    """Selecting a folder selects the files directly inside it"""
    find_item(library_item, root / 'Sub A').setSelected(True)
    find_item(library_item, root / 'song 2.txt').setSelected(True)
    assert sorted(library_item.selected_file_paths()) == sorted([root / 'Sub A' / 'a.txt', root / 'song 2.txt'])


def test_create_item_from_id(library_item, root):
    """An item can be created from a path string, for the remote API"""
    tree_item = library_item.create_item_from_id(str(root / 'song 2.txt'))
    assert tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole) == root / 'song 2.txt'
    assert tree_item.data(0, ItemTypeRole) == ItemType.File


def test_directory_change_triggers_reload(library_item, root, qtbot):
    """Changes on disk are picked up automatically"""
    # WHEN: A file is created on disk
    (root / 'Sub B' / 'added.txt').write_text('x')

    # THEN: The library picks it up
    qtbot.waitUntil(lambda: root / 'Sub B' / 'added.txt' in library_item.get_file_list(), timeout=5000)
