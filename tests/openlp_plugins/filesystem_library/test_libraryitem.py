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
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole


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


def test_portable_root_is_saved_relative(registry, settings, temp_folder):
    """In a portable OpenLP a root folder inside the portable folder survives moving the whole folder"""
    # GIVEN: A portable OpenLP with a library inside it and another one outside it
    registry.register('main_window', MagicMock())
    portable, moved = Path(temp_folder) / 'portable', Path(temp_folder) / 'moved'
    (portable / 'Songs').mkdir(parents=True)
    (moved / 'Songs').mkdir(parents=True)
    outside = Path(temp_folder) / 'outside'
    outside.mkdir()
    settings.setValue('advanced/is portable', True)
    settings.setValue('advanced/data path', portable / 'Data')
    item = TextLibraryItem(None, make_plugin())

    # WHEN: The folder inside the portable folder is chosen and the portable folder is moved
    item.root_path = portable / 'Songs'
    stored = settings.value('test_library/root folder')
    settings.setValue('advanced/data path', moved / 'Data')

    # THEN: The folder is saved relative and found in the new place
    assert stored == Path('Songs')
    assert item.root_path == moved / 'Songs'

    # WHEN: A folder outside the portable folder is chosen
    item.root_path = outside

    # THEN: It is saved as it is
    assert settings.value('test_library/root folder') == outside
    assert item.root_path == outside


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


@patch('openlp.plugins.filesystem_library.libraryitem.critical_error_message_box')
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


class RelatedLibraryItem(TextLibraryItem):
    """A library item where a ".note" file belongs to each text file"""
    def related_files(self, file_path):
        note = file_path.with_suffix('.note')
        return [note] if note.exists() else []


@pytest.fixture
def related_item(registry, settings, root):
    registry.register('main_window', MagicMock())
    settings.setValue('test_library/root folder', root)
    (root / 'song 2.note').write_text('note')
    item = RelatedLibraryItem(None, make_plugin())
    item.initialise()
    yield item
    item._reload_timer.stop()


def test_dnd_move_internal_moves_related_files(related_item, root):
    """The related files of a file are moved with it"""
    find_item(related_item, root / 'song 2.txt').setSelected(True)

    related_item.dnd_move_internal(find_item(related_item, root / 'Sub B'))

    assert (root / 'Sub B' / 'song 2.note').read_text() == 'note'
    assert not (root / 'song 2.note').exists()


@patch('openlp.plugins.filesystem_library.libraryitem.critical_error_message_box')
def test_dnd_move_internal_keeps_existing_related_files(mocked_error, related_item, root):
    """Related files are not overwritten when the file is moved"""
    (root / 'Sub B' / 'song 2.note').write_text('other')
    find_item(related_item, root / 'song 2.txt').setSelected(True)

    related_item.dnd_move_internal(find_item(related_item, root / 'Sub B'))

    assert (root / 'Sub B' / 'song 2.txt').exists()
    assert (root / 'Sub B' / 'song 2.note').read_text() == 'other'
    assert (root / 'song 2.note').exists()
    mocked_error.assert_called_once()


def test_validate_and_load_copies_related_files(related_item, root, temp_folder):
    """The related files of a file from outside the library are copied with it"""
    outside = Path(temp_folder) / 'new.txt'
    outside.write_text('new')
    outside.with_suffix('.note').write_text('new note')

    related_item.validate_and_load([outside], find_item(related_item, root / 'Sub B'))

    assert (root / 'Sub B' / 'new.note').read_text() == 'new note'
    assert outside.with_suffix('.note').exists()


@patch('openlp.plugins.filesystem_library.libraryitem.move_to_trash', return_value=True)
@patch('openlp.plugins.filesystem_library.libraryitem.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Yes)
def test_delete_moves_related_files_to_trash(mocked_question, mocked_trash, related_item, root):
    """The related files of a file are moved to the trash with it"""
    find_item(related_item, root / 'song 2.txt').setSelected(True)

    related_item.on_delete_click()

    assert [call.args[0] for call in mocked_trash.call_args_list] == [root / 'song 2.txt', root / 'song 2.note']


def test_dnd_move_folder_into_itself_is_ignored(library_item, root):
    """A folder cannot be moved inside itself"""
    find_item(library_item, root / 'Sub A').setSelected(True)
    library_item.dnd_move_internal(find_item(library_item, root / 'Sub A' / 'Deep'))
    assert (root / 'Sub A' / 'Deep').is_dir()


@patch('openlp.plugins.filesystem_library.libraryitem.move_to_trash')
@patch('openlp.plugins.filesystem_library.libraryitem.QtWidgets.QMessageBox.question')
def test_delete_moves_to_trash(mocked_question, mocked_trash, library_item, root):
    """Deleting asks first and moves the files to the trash"""
    # GIVEN: A selected folder and a user who says yes
    mocked_question.return_value = QtWidgets.QMessageBox.StandardButton.Yes
    mocked_trash.return_value = True
    existed = []
    library_item.delete_item = MagicMock(side_effect=lambda path: existed.append(path.exists()))
    find_item(library_item, root / 'Sub A').setSelected(True)

    # WHEN: Delete is clicked
    library_item.on_delete_click()

    # THEN: The folder is trashed and the files in it are cleaned up while they still exist
    mocked_trash.assert_called_once_with(root / 'Sub A')
    assert existed == [True, True]
    assert sorted(call.args[0] for call in library_item.delete_item.call_args_list) == \
        sorted([root / 'Sub A' / 'a.txt', root / 'Sub A' / 'Deep' / 'deep.txt'])


@patch('openlp.plugins.filesystem_library.libraryitem.move_to_trash')
@patch('openlp.plugins.filesystem_library.libraryitem.QtWidgets.QMessageBox.question')
def test_delete_cancelled(mocked_question, mocked_trash, library_item, root):
    """Nothing is deleted when the user says no"""
    mocked_question.return_value = QtWidgets.QMessageBox.StandardButton.No
    find_item(library_item, root / 'song 2.txt').setSelected(True)
    library_item.on_delete_click()
    mocked_trash.assert_not_called()


@patch('openlp.plugins.filesystem_library.libraryitem.QtWidgets.QInputDialog.getText')
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


def test_create_item_from_id_outside_root(library_item, temp_folder):
    """Paths outside the library folder get no item type, so they cannot be shown through the remote API"""
    outside = Path(temp_folder) / 'outside.txt'
    outside.write_text('x')
    tree_item = library_item.create_item_from_id(str(outside))
    assert tree_item.data(0, ItemTypeRole) is None


def test_folder_files(library_item, root):
    """folder_files() lists the supported files directly inside a folder in natural order"""
    assert library_item.folder_files(root) == [root / 'song 2.txt', root / 'song 10.txt']
    assert library_item.folder_files(root / 'missing') == []


def test_directory_change_triggers_reload(library_item, root, qtbot):
    """Changes on disk are picked up automatically"""
    # WHEN: A file is created on disk
    (root / 'Sub B' / 'added.txt').write_text('x')

    # THEN: The library picks it up
    qtbot.waitUntil(lambda: root / 'Sub B' / 'added.txt' in library_item.get_file_list(), timeout=5000)
