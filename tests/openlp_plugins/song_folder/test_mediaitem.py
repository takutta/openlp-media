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
from openlp.plugins.song_folder.lib.songfile import SongFileError
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


def test_generate_slide_data_can_edit(media_item, song_root):
    """The service item can be edited, and remembers its file"""
    service_item = ServiceItem(media_item.plugin)
    media_item.generate_slide_data(service_item, item=find_item(media_item, song_root / 'b-song.xml'))

    assert service_item.is_capable(ItemCapabilities.CanEdit)
    assert service_item.edit_id == str(song_root / 'b-song.xml')


def test_service_load_restores_edit_id(media_item, song_root):
    """A song loaded from a service file can be edited if its file still exists"""
    service_item = ServiceItem(None)
    service_item.add_capability(ItemCapabilities.CanEdit)
    service_item.data_string = {'file path': str(song_root / 'b-song.xml')}
    media_item.service_load(service_item)
    assert service_item.edit_id == str(song_root / 'b-song.xml')

    service_item = ServiceItem(None)
    service_item.add_capability(ItemCapabilities.CanEdit)
    service_item.data_string = {'file path': str(song_root / 'gone.xml')}
    media_item.service_load(service_item)
    assert not service_item.is_capable(ItemCapabilities.CanEdit)


def accept_form(media_item, change):
    """Make the edit form change the song and return Accepted instead of showing it"""
    def exec_form():
        change(media_item.edit_song_form)
        return QtWidgets.QDialog.DialogCode.Accepted
    media_item.edit_song_form.exec = exec_form


def test_on_new_click_creates_file(media_item, song_root):
    """A new song is saved to a new file in the selected folder"""
    find_item(media_item, song_root / 'Hymns').setSelected(True)

    def change(form):
        form.title_edit.setText('Uusi: laulu')
        form.lyrics_edit.setPlainText('---[Verse:1]---\nUusi säe')
    accept_form(media_item, change)

    media_item.on_new_click()

    file_path = song_root / 'Hymns' / 'Uusi_ laulu.xml'
    assert media_item.index.get(file_path).verses[0].text == 'Uusi säe'
    assert find_item(media_item, file_path).isSelected()


def test_on_new_click_cancelled(media_item, song_root):
    """Nothing is written when the form is cancelled"""
    media_item.edit_song_form.exec = lambda: QtWidgets.QDialog.DialogCode.Rejected
    files = sorted(song_root.rglob('*'))

    media_item.on_new_click()

    assert sorted(song_root.rglob('*')) == files


def test_on_edit_click_saves_and_updates_service(media_item, song_root):
    """Editing saves to the same file and updates the copies of the song in the service"""
    file_path = song_root / 'b-song.xml'
    tree_item = find_item(media_item, file_path)
    media_item.list_view.setCurrentItem(tree_item)
    old_item = ServiceItem(media_item.plugin)
    old_item.edit_id = str(file_path)
    media_item.service_manager.service_items = [{'service_item': old_item}]
    accept_form(media_item, lambda form: form.title_edit.setText('Beta (edited)'))

    media_item.on_edit_click()

    assert media_item.index.get(file_path).title == 'Beta (edited)'
    assert b'<tempo' not in file_path.read_bytes()
    new_item = media_item.service_manager.replace_service_item.call_args.args[0]
    assert new_item.title == 'Beta (edited)'


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
def test_edit_broken_file_shows_error(mocked_error, media_item, song_root):
    """A file which cannot be read cannot be edited"""
    assert media_item.edit_song_file(song_root / 'Hymns' / 'broken.xml') is False
    mocked_error.assert_called_once()


def test_on_remote_edit(media_item, song_root):
    """Editing from the service returns the new service item"""
    accept_form(media_item, lambda form: form.title_edit.setText('Remote edit'))

    item = media_item.on_remote_edit(str(song_root / 'b-song.xml'), preview=True)

    assert item.title == 'Remote edit'
    assert item.from_plugin is True


@patch('openlp.plugins.song_folder.lib.mediaitem.write_song_file', side_effect=SongFileError('read-only'))
@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
def test_save_failure_shows_error(mocked_error, mocked_write, media_item, song_root):
    """A song which cannot be saved shows an error"""
    accept_form(media_item, lambda form: None)

    assert media_item.edit_song_file(song_root / 'b-song.xml') is False
    mocked_error.assert_called_once()
