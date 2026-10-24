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
Test the song folder plugin's media item
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6 import QtCore, QtWidgets

from openlp.core.common.actions import ActionList
from openlp.core.lib.serviceitem import ItemCapabilities, ServiceItem
from openlp.plugins.song_folder.lib.mediaitem import SongFolderMediaItem
from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse, parse_song_file
from openlp.plugins.songs.songsplugin import song_footer


SONG = '''<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.8">
  <properties>
    <titles><title>{title}</title></titles>
    <authors><author type="words">Words Writer</author><author>Someone</author></authors>
    <copyright>Public Domain</copyright>
    <ccliNo>42</ccliNo>
    <verseOrder>v1 c1 v1</verseOrder>
    <songbooks><songbook name="Book" entry="7"/></songbooks>
  </properties>
  <lyrics>
    <verse name="v1"><lines>Verse line<p style="page-break-after: always;"/>Second page</lines></verse>
    <verse name="c1"><lines>{chorus}</lines></verse>
  </lyrics>
</song>'''


@pytest.fixture
def song_root(temp_folder):
    root = Path(temp_folder) / 'songs'
    (root / 'Hymns').mkdir(parents=True)
    (root / 'b-song.xml').write_text(SONG.format(title='Beta', chorus='Hallelujah'))
    (root / 'Hymns' / 'a-song.XML').write_text(SONG.format(title='Alpha', chorus='Glory'))
    (root / 'Hymns' / 'broken.xml').write_text('not xml')
    (root / 'notes.txt').write_text('')
    return root


@pytest.fixture
def media_item(registry, settings, state, song_root):
    ActionList.shortcut_map = {}
    settings.extend_default_settings(song_footer)
    registry.register('main_window', MagicMock())
    registry.register('service_manager', MagicMock(**{'get_drop_position.return_value': -1}))
    settings.setValue('song_folder/root folder', song_root)
    plugin = MagicMock()
    plugin.name = 'song_folder'
    plugin.get_string.return_value = {'title': 'Song Folder', 'tooltip': 'Tooltip'}
    item = SongFolderMediaItem(None, plugin)
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


def test_only_xml_files_are_listed(media_item, song_root):
    """OpenLyrics files are listed regardless of the case of the extension, and their titles are shown"""
    assert sorted(media_item.get_file_list()) == sorted([song_root / 'b-song.xml', song_root / 'Hymns' / 'a-song.XML',
                                                         song_root / 'Hymns' / 'broken.xml'])
    assert find_item(media_item, song_root / 'b-song.xml').text(0) == 'Beta'
    assert find_item(media_item, song_root / 'Hymns' / 'a-song.XML').text(0) == 'Alpha'
    # A file that cannot be read is shown with its file name
    assert find_item(media_item, song_root / 'Hymns' / 'broken.xml').text(0) == 'broken.xml'
    assert len(media_item.index) == 3


def test_filter_list(media_item, song_root):
    """Searching hides the songs which do not match and the folders without matches"""
    # WHEN: Searching for the chorus of one song
    media_item.search_text_edit.setText('glory')

    # THEN: Only that song and its folder are shown
    assert find_item(media_item, song_root / 'b-song.xml').isHidden()
    assert not find_item(media_item, song_root / 'Hymns' / 'a-song.XML').isHidden()
    assert find_item(media_item, song_root / 'Hymns' / 'broken.xml').isHidden()
    hymns = find_item(media_item, song_root / 'Hymns')
    assert not hymns.isHidden()
    assert hymns.isExpanded()

    # WHEN: Searching for something which is only in the other song
    media_item.search_text_edit.setText('hallelujah')

    # THEN: The folder is hidden
    assert hymns.isHidden()

    # WHEN: The search is cleared
    media_item.search_text_edit.setText('')

    # THEN: Everything is shown again
    assert not hymns.isHidden()
    assert not find_item(media_item, song_root / 'b-song.xml').isHidden()


def test_filter_is_kept_on_reload(media_item, song_root):
    """When the folder changes on disk, the list is filtered again"""
    media_item.search_text_edit.setText('glory')
    (song_root / 'new.xml').write_text(SONG.format(title='Gamma', chorus='Glory again'))

    media_item.reload()

    assert not find_item(media_item, song_root / 'new.xml').isHidden()
    assert find_item(media_item, song_root / 'b-song.xml').isHidden()


def test_remote_search(media_item, song_root):
    """The remote API search returns the path and the titles"""
    assert media_item.search('hallelujah') == [[str(song_root / 'b-song.xml'), 'Beta', '']]


def test_generate_slide_data(media_item, song_root, settings):
    """The slides follow the verse order and the footer is built"""
    # GIVEN: A service item and a song in the library
    settings.setValue('core/ccli number', '9999')
    service_item = ServiceItem(media_item.plugin)
    tree_item = find_item(media_item, song_root / 'b-song.xml')

    # WHEN: Generating the slide data
    result = media_item.generate_slide_data(service_item, item=tree_item)

    # THEN: The slides, the footer and the data of the song are set
    assert result is True
    assert service_item.title == 'Beta'
    texts = [slide['text'] for slide in service_item.slides]
    assert texts == ['Verse line', 'Second page', 'Hallelujah', 'Verse line', 'Second page']
    assert [slide['verse'] for slide in service_item.slides] == ['V1', 'V1', 'C1', 'V1', 'V1']
    assert service_item.raw_footer == ['Beta', 'Written by: Someone', 'Words: Words Writer', '© Public Domain',
                                       'Book #7', 'CCLI License: 9999']
    assert 'Words Writer' in service_item.footer_html
    assert service_item.audit == ['Beta', ['Words Writer', 'Someone'], 'Public Domain', '42']
    assert service_item.data_string['file path'] == str(song_root / 'b-song.xml')
    assert service_item.is_capable(ItemCapabilities.CanSoftBreak)
    assert service_item.is_capable(ItemCapabilities.OnLoadUpdate)
    assert service_item.icon is not None


def test_generate_slide_data_for_folder(media_item, song_root):
    """A folder cannot be turned into a service item"""
    assert media_item.generate_slide_data(ServiceItem(None), item=find_item(media_item, song_root / 'Hymns')) is False


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
def test_generate_slide_data_broken_file(mocked_error, media_item, song_root):
    """A file which cannot be read shows an error"""
    tree_item = find_item(media_item, song_root / 'Hymns' / 'broken.xml')

    assert media_item.generate_slide_data(ServiceItem(None), item=tree_item) is False
    mocked_error.assert_called_once()


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
def test_generate_slide_data_remote_shows_no_error(mocked_error, media_item, song_root):
    """No error box is shown for the remote API"""
    tree_item = media_item.create_item_from_id(song_root / 'gone.xml')

    assert media_item.generate_slide_data(ServiceItem(None), item=tree_item, remote=True) is False
    mocked_error.assert_not_called()


def test_service_load_sets_icon(media_item):
    """A service item loaded from a service file gets its icon back"""
    service_item = ServiceItem(None)
    service_item.icon = None

    assert media_item.service_load(service_item) is service_item
    assert service_item.icon is not None


def test_on_add_click_adds_every_song_in_selected_folder(media_item, song_root):
    """Adding a folder to the service adds each song in it"""
    media_item.add_to_service = MagicMock()
    find_item(media_item, song_root / 'Hymns').setSelected(True)

    media_item.on_add_click()

    added = [call.args[0].data(0, QtCore.Qt.ItemDataRole.UserRole) for call in media_item.add_to_service.call_args_list]
    assert added == [song_root / 'Hymns' / 'a-song.XML', song_root / 'Hymns' / 'broken.xml']


def test_delete_item_forgets_song(media_item, song_root):
    """A song that was moved to the trash is removed from the index"""
    media_item.delete_item(song_root / 'b-song.xml')

    assert song_root / 'b-song.xml' not in media_item.index


def test_generate_slide_data_can_be_edited(media_item, song_root):
    """The song can be edited from the service and the preview, the edit id is the path of the file"""
    service_item = ServiceItem(media_item.plugin)

    media_item.generate_slide_data(service_item, item=find_item(media_item, song_root / 'b-song.xml'))

    assert service_item.is_capable(ItemCapabilities.CanEdit)
    assert service_item.edit_id == str(song_root / 'b-song.xml')


def test_service_load_sets_edit_id(media_item, song_root):
    """The edit id is not saved in service files, so it is restored from the path of the song"""
    service_item = ServiceItem(None)
    service_item.data_string = {'file path': str(song_root / 'b-song.xml')}

    media_item.service_load(service_item)

    assert service_item.edit_id == str(song_root / 'b-song.xml')


def mock_editor(media_item, song=None, accepted=True):
    """Replace the song editor with one that returns a song"""
    form = MagicMock()
    form.exec.return_value = \
        QtWidgets.QDialog.DialogCode.Accepted if accepted else QtWidgets.QDialog.DialogCode.Rejected
    form.load_song.side_effect = lambda loaded: setattr(form, 'song', song or loaded)
    media_item._edit_song_form = form
    return form


def test_on_new_click_writes_song_into_selected_folder(media_item, song_root):
    """A new song is written into the selected folder, named after its title, and selected"""
    form = mock_editor(media_item, FileSong(titles=['New: song'], verses=[SongVerse('v', text='Line')]))
    find_item(media_item, song_root / 'Hymns' / 'a-song.XML').setSelected(True)

    media_item.on_new_click()

    form.load_song.assert_called_once_with(None)
    new_path = song_root / 'Hymns' / 'New_ song.xml'
    assert parse_song_file(new_path).title == 'New: song'
    assert find_item(media_item, new_path).isSelected()
    assert find_item(media_item, new_path).text(0) == 'New: song'


@patch('openlp.plugins.filesystem_library.libraryitem.critical_error_message_box')
def test_on_new_click_without_folder(mocked_error, media_item, settings):
    """A folder needs to be chosen before a song can be added"""
    settings.setValue('song_folder/root folder', None)
    form = mock_editor(media_item)

    media_item.on_new_click()

    mocked_error.assert_called_once()
    form.exec.assert_not_called()


def edit_song(song):
    song.titles[0] = 'Edited'
    song.verses[0].text = 'New line'
    return song


def test_on_edit_click_saves_song_and_updates_service(media_item, song_root):
    """The edited song is written to its file, keeping what the editor does not know, and updated in the service"""
    # GIVEN: A song with a property the editor does not know about
    file_path = song_root / 'b-song.xml'
    file_path.write_text(SONG.format(title='Beta', chorus='Hallelujah').replace('<ccliNo>', '<key>G</key><ccliNo>'))
    media_item.reload()
    form = mock_editor(media_item)
    form.load_song.side_effect = lambda loaded: setattr(form, 'song', edit_song(loaded))
    find_item(media_item, file_path).setSelected(True)
    media_item.list_view.setCurrentItem(find_item(media_item, file_path))

    # WHEN: Editing it
    media_item.on_edit_click()

    # THEN: The file has the changes and the unknown property, and the service is updated
    song = parse_song_file(file_path)
    assert song.title == 'Edited'
    assert song.verses[0].text == 'New line'
    assert b'<key>G</key>' in file_path.read_bytes()
    assert find_item(media_item, file_path).text(0) == 'Edited'
    service_item = media_item.service_manager.replace_service_item.call_args.args[0]
    assert service_item.edit_id == str(file_path)
    assert service_item.title == 'Edited'


def test_on_edit_click_cancelled(media_item, song_root):
    """Nothing is written if the editor is cancelled"""
    file_path = song_root / 'b-song.xml'
    original = file_path.read_bytes()
    mock_editor(media_item, accepted=False)
    media_item.list_view.setCurrentItem(find_item(media_item, file_path))

    media_item.on_edit_click()

    assert file_path.read_bytes() == original
    media_item.service_manager.replace_service_item.assert_not_called()


@patch('openlp.plugins.song_folder.lib.mediaitem.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.No)
def test_edit_song_file_changed_on_disk(mocked_question, media_item, song_root):
    """The user is asked before a file which changed while it was edited is overwritten"""
    file_path = song_root / 'b-song.xml'
    form = mock_editor(media_item)

    def change_file():
        file_path.write_text(SONG.format(title='Other', chorus='x'))
        return QtWidgets.QDialog.DialogCode.Accepted
    form.exec.side_effect = change_file

    assert media_item.edit_song_file(file_path) is None

    mocked_question.assert_called_once()
    assert parse_song_file(file_path).title == 'Other'


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
def test_edit_song_file_broken(mocked_error, media_item, song_root):
    """A file which cannot be read is not opened in the editor"""
    form = mock_editor(media_item)

    assert media_item.edit_song_file(song_root / 'Hymns' / 'broken.xml') is None

    mocked_error.assert_called_once()
    form.exec.assert_not_called()


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
@patch('openlp.plugins.song_folder.lib.mediaitem.write_song_file')
def test_edit_song_file_write_error_reopens_editor(mocked_write, mocked_error, media_item, song_root):
    """If the song cannot be saved, the editor is shown again with the song"""
    mocked_write.side_effect = [OSError('disk full'), None]
    form = mock_editor(media_item)

    assert media_item.edit_song_file(song_root / 'b-song.xml') == song_root / 'b-song.xml'

    mocked_error.assert_called_once()
    assert form.exec.call_count == 2
    form.load_song.assert_called_once()


@pytest.mark.parametrize('preview', [True, False])
def test_on_remote_edit(media_item, song_root, preview):
    """Editing from the service or the preview returns the new service item"""
    form = mock_editor(media_item)
    form.load_song.side_effect = lambda loaded: setattr(form, 'song', edit_song(loaded))

    service_item = media_item.on_remote_edit(str(song_root / 'b-song.xml'), preview)

    assert service_item.title == 'Edited'
    assert service_item.from_plugin is preview


def test_on_remote_edit_outside_library(media_item, temp_folder):
    """Files outside the library are not edited"""
    outside = Path(temp_folder) / 'outside.xml'
    outside.write_text(SONG.format(title='Outside', chorus='x'))
    form = mock_editor(media_item)

    assert media_item.on_remote_edit(str(outside)) is None
    form.exec.assert_not_called()
