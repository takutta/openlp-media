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
from openlp.core.common.registry import Registry
from openlp.core.state import State
from openlp.plugins.song_folder.lib.songindex import SongIndex
from openlp.plugins.song_folder.lib.songfile import FileSong, SongFileError, SongVerse, parse_song_file
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
def media_item(registry, settings, state, song_root, temp_folder):
    ActionList.shortcut_map = {}
    settings.extend_default_settings(song_footer)
    registry.register('main_window', MagicMock())
    registry.register('service_manager', MagicMock(**{'get_drop_position.return_value': -1}))
    settings.setValue('song_folder/root folder', song_root)
    plugin = MagicMock()
    plugin.name = 'song_folder'
    plugin.get_string.return_value = {'title': 'Song Folder', 'tooltip': 'Tooltip'}
    with patch('openlp.plugins.song_folder.lib.mediaitem.AppLocation.get_section_data_path',
               return_value=Path(temp_folder) / 'data'):
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


def test_service_load_missing_file_cannot_be_edited(media_item, song_root):
    """A song whose file is gone cannot be edited"""
    service_item = ServiceItem(None)
    service_item.add_capability(ItemCapabilities.CanEdit)
    service_item.data_string = {'file path': str(song_root / 'gone.xml')}

    media_item.service_load(service_item)

    assert not service_item.is_capable(ItemCapabilities.CanEdit)
    assert service_item.edit_id is None


def mock_editor(media_item, song=None, accepted=True):
    """Replace the song editor with one that returns a song"""
    form = MagicMock()
    form.exec.return_value = \
        QtWidgets.QDialog.DialogCode.Accepted if accepted else QtWidgets.QDialog.DialogCode.Rejected
    form.audio_path = None

    def load_song(loaded, audio_path=None):
        form.song = song or loaded
        form.audio_path = audio_path
    form.load_song.side_effect = load_song
    media_item._edit_song_form = form
    return form


def test_on_new_click_writes_song_into_selected_folder(media_item, song_root):
    """A new song is written into the selected folder, named after its title, and selected"""
    form = mock_editor(media_item, FileSong(titles=['New: song'], verses=[SongVerse('v', text='Line')]))
    find_item(media_item, song_root / 'Hymns' / 'a-song.XML').setSelected(True)

    media_item.on_new_click()

    form.load_song.assert_called_once_with(None, None)
    new_path = song_root / 'Hymns' / 'New_ song.xml'
    assert parse_song_file(new_path).title == 'New: song'
    assert find_item(media_item, new_path).isSelected()
    assert find_item(media_item, new_path).text(0) == 'New: song'


def test_on_new_click_cancelled(media_item, song_root):
    """Nothing is written if the editor is cancelled"""
    files = sorted(song_root.rglob('*'))
    mock_editor(media_item, accepted=False)

    media_item.on_new_click()

    assert sorted(song_root.rglob('*')) == files


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
    form.load_song.side_effect = lambda loaded, audio_path=None: setattr(form, 'song', edit_song(loaded))
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
    mocked_write.side_effect = [SongFileError('disk full'), None]
    form = mock_editor(media_item)

    assert media_item.edit_song_file(song_root / 'b-song.xml') == song_root / 'b-song.xml'

    mocked_error.assert_called_once()
    assert form.exec.call_count == 2
    form.load_song.assert_called_once()


@pytest.mark.parametrize('preview', [True, False])
def test_on_remote_edit(media_item, song_root, preview):
    """Editing from the service or the preview returns the new service item"""
    form = mock_editor(media_item)
    form.load_song.side_effect = lambda loaded, audio_path=None: setattr(form, 'song', edit_song(loaded))

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


def slide_texts(media_item, file_path):
    service_item = ServiceItem(media_item.plugin)
    media_item.generate_slide_data(service_item, item=find_item(media_item, file_path))
    return service_item, [slide['text'] for slide in service_item.slides]


def test_uppercase_songs(media_item, song_root, settings):
    """The slides are in upper case when the Songs plugin is set so"""
    settings.setValue('songs/uppercase songs', True)

    _, texts = slide_texts(media_item, song_root / 'b-song.xml')

    assert texts[0] == '{uc}Verse line{/uc}'


@pytest.mark.parametrize('mode, text, verse', [(1, '\nBook #7\n\n', 'O1'), (2, None, 'O2')])
def test_first_slide(media_item, song_root, settings, mode, text, verse):
    """The first slide shows the songbooks or the footer, like in the Songs plugin"""
    settings.setValue('songs/first slide mode', mode)

    service_item, texts = slide_texts(media_item, song_root / 'b-song.xml')

    assert service_item.slides[0]['verse'] == verse
    if text:
        assert texts[0] == text
    else:
        assert 'Beta' in texts[0]
    assert texts[1] == 'Verse line'


def test_preview_of_next_line(media_item, song_root, settings):
    """The first line of the next slide is shown at the end of a slide"""
    settings.setValue('songs/preview_enabled', True)
    settings.setValue('songs/preview_chorus', False)

    _, texts = slide_texts(media_item, song_root / 'b-song.xml')

    # Verse 1 previews its next page and the following verse 1 page, the chorus is not previewed into or out of
    assert texts[0] == 'Verse line\n{preview}Second page{/preview}'
    assert texts[1] == 'Second page'
    assert texts[2] == 'Hallelujah'


def test_background_audio(media_item, song_root, state):
    """An audio file with the same name as the song is played in the background"""
    State().add_service('media', 0)
    State().update_pre_conditions('media', True)
    State().flush_preconditions()
    Registry().register('media_controller', MagicMock(**{'media_length.return_value': 4321}))
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    (song_root / 'b-song-other.mp3').write_bytes(b'audio')

    with patch('openlp.plugins.song_folder.lib.mediaitem.get_supported_media_suffix',
               return_value=(['*.mp3'], ['*.mp4'])):
        service_item, _ = slide_texts(media_item, song_root / 'b-song.xml')

    assert service_item.is_capable(ItemCapabilities.HasBackgroundAudio)
    assert service_item.background_audio[0][0] == song_root / 'b-song.mp3'
    assert service_item.media_length == 4321


def test_no_background_audio(media_item, song_root):
    """Without an audio file the song has no background audio"""
    with patch('openlp.plugins.song_folder.lib.mediaitem.get_supported_media_suffix',
               return_value=(['*.mp3'], ['*.mp4'])):
        service_item, _ = slide_texts(media_item, song_root / 'b-song.xml')

    assert not service_item.is_capable(ItemCapabilities.HasBackgroundAudio)


def test_song_theme(media_item, song_root):
    """The theme of the song is used for its slides"""
    file_path = song_root / 'b-song.xml'
    file_path.write_text(SONG.format(title='Beta', chorus='x').replace(
        '</song>', '<theme xmlns="http://openlp.org/ns/song-folder">Dark</theme></song>'))

    service_item, _ = slide_texts(media_item, file_path)

    assert service_item.theme == 'Dark'


def test_index_cache(media_item, song_root):
    """The search index is saved to its cache and read back"""
    assert media_item.index_cache_path.exists()
    index = SongIndex()
    index.load(media_item.index_cache_path)

    assert index.get(song_root / 'b-song.xml').title == 'Beta'
    assert index.error(song_root / 'Hymns' / 'broken.xml')
    assert not index.changed


def audio_suffixes():
    return patch('openlp.plugins.song_folder.lib.mediaitem.get_supported_media_suffix',
                 return_value=(['', '*.mp3', '*.ogg'], ['*.mp4']))


def choose_audio(form, audio_path):
    """Make the mocked editor return an audio file"""
    load_song = form.load_song.side_effect

    def choose(*args):
        load_song(*args)
        form.audio_path = audio_path
    form.load_song.side_effect = choose


def test_background_audio_files(media_item, song_root):
    """Only audio files with exactly the name of the song belong to it"""
    for name in ['b-song.mp3', 'b-song.OGG', 'b-song.txt', 'b-song.extra.mp3', 'b-song-other.mp3']:
        (song_root / name).write_bytes(b'audio')

    with audio_suffixes():
        assert set(media_item.related_files(song_root / 'b-song.xml')) == {song_root / 'b-song.OGG',
                                                                           song_root / 'b-song.mp3'}


def test_edit_song_shows_background_audio(media_item, song_root):
    """The editor is given the audio file of the song"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    form = mock_editor(media_item, accepted=False)

    with audio_suffixes():
        media_item.edit_song_file(song_root / 'b-song.xml')

    assert form.load_song.call_args.args[1] == song_root / 'b-song.mp3'


@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash')
def test_edit_song_chooses_background_audio(mocked_trash, media_item, song_root, temp_folder):
    """A chosen audio file is copied next to the song and the old audio file is moved to the trash"""
    # GIVEN: A song with an audio file, and another audio file outside the library
    (song_root / 'b-song.mp3').write_bytes(b'old')
    chosen = Path(temp_folder) / 'Chosen.ogg'
    chosen.write_bytes(b'new')
    mocked_trash.side_effect = lambda path: path.unlink() is None
    choose_audio(mock_editor(media_item), chosen)

    # WHEN: The song is saved
    with audio_suffixes():
        media_item.edit_song_file(song_root / 'b-song.xml')

    # THEN: The chosen file is the audio of the song
    mocked_trash.assert_called_once_with(song_root / 'b-song.mp3')
    assert (song_root / 'b-song.ogg').read_bytes() == b'new'
    assert chosen.exists()


@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash', return_value=True)
def test_edit_song_keeps_background_audio(mocked_trash, media_item, song_root):
    """Audio files are left alone when the audio is not changed"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    (song_root / 'b-song.ogg').write_bytes(b'audio')
    mock_editor(media_item)

    with audio_suffixes():
        media_item.edit_song_file(song_root / 'b-song.xml')

    mocked_trash.assert_not_called()


@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash', return_value=True)
def test_edit_song_removes_background_audio(mocked_trash, media_item, song_root):
    """Removing the audio in the editor moves the audio files of the song to the trash"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    (song_root / 'b-song.ogg').write_bytes(b'audio')
    choose_audio(mock_editor(media_item), None)

    with audio_suffixes():
        media_item.edit_song_file(song_root / 'b-song.xml')

    assert [call.args[0] for call in mocked_trash.call_args_list] == [song_root / 'b-song.mp3',
                                                                      song_root / 'b-song.ogg']


@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash', return_value=True)
def test_edit_song_chooses_other_audio_of_song(mocked_trash, media_item, song_root):
    """Choosing the second audio file of a song moves the first one to the trash"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    (song_root / 'b-song.ogg').write_bytes(b'audio')
    choose_audio(mock_editor(media_item), song_root / 'b-song.ogg')

    with audio_suffixes():
        media_item.edit_song_file(song_root / 'b-song.xml')

    mocked_trash.assert_called_once_with(song_root / 'b-song.mp3')


@patch('openlp.plugins.song_folder.lib.mediaitem.critical_error_message_box')
@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash', return_value=False)
def test_edit_song_background_audio_error(mocked_trash, mocked_error, media_item, song_root, temp_folder):
    """The user is told if the audio cannot be changed, but the song is saved"""
    (song_root / 'b-song.mp3').write_bytes(b'old')
    choose_audio(mock_editor(media_item, edit_song(parse_song_file(song_root / 'b-song.xml'))),
                 Path(temp_folder) / 'missing.mp3')

    with audio_suffixes():
        assert media_item.edit_song_file(song_root / 'b-song.xml') == song_root / 'b-song.xml'

    mocked_error.assert_called_once()
    assert parse_song_file(song_root / 'b-song.xml').title == 'Edited'


@patch('openlp.plugins.song_folder.lib.mediaitem.move_to_trash', return_value=True)
def test_new_song_leaves_audio_with_its_name(mocked_trash, media_item, song_root):
    """A new song without audio does not remove an audio file which happens to have its name"""
    (song_root / 'New.mp3').write_bytes(b'audio')
    mock_editor(media_item, FileSong(titles=['New'], verses=[SongVerse('v', text='Line')]))

    with audio_suffixes():
        media_item.on_new_click()

    assert (song_root / 'New.xml').exists()
    mocked_trash.assert_not_called()


def test_new_song_with_background_audio(media_item, song_root, temp_folder):
    """The audio chosen for a new song is copied next to it"""
    chosen = Path(temp_folder) / 'chosen.mp3'
    chosen.write_bytes(b'audio')
    choose_audio(mock_editor(media_item, FileSong(titles=['New'], verses=[SongVerse('v', text='Line')])), chosen)

    with audio_suffixes():
        media_item.on_new_click()

    assert (song_root / 'New.mp3').read_bytes() == b'audio'


def test_move_song_moves_audio(media_item, song_root):
    """The audio file moves together with the song"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    find_item(media_item, song_root / 'b-song.xml').setSelected(True)

    with audio_suffixes():
        media_item.dnd_move_internal(find_item(media_item, song_root / 'Hymns'))

    assert (song_root / 'Hymns' / 'b-song.xml').exists()
    assert (song_root / 'Hymns' / 'b-song.mp3').read_bytes() == b'audio'
    assert not (song_root / 'b-song.mp3').exists()


@patch('openlp.plugins.filesystem_library.libraryitem.move_to_trash', return_value=True)
@patch('openlp.plugins.filesystem_library.libraryitem.QtWidgets.QMessageBox.question',
       return_value=QtWidgets.QMessageBox.StandardButton.Yes)
def test_delete_song_deletes_audio(mocked_question, mocked_trash, media_item, song_root):
    """The audio file is moved to the trash together with the song"""
    (song_root / 'b-song.mp3').write_bytes(b'audio')
    find_item(media_item, song_root / 'b-song.xml').setSelected(True)

    with audio_suffixes():
        media_item.on_delete_click()

    assert [call.args[0] for call in mocked_trash.call_args_list] == [song_root / 'b-song.xml',
                                                                      song_root / 'b-song.mp3']
