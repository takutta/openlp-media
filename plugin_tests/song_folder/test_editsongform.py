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
Test the song editor of the song folder plugin
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from openlp.core.common.i18n import UiStrings
from openlp.plugins.song_folder.forms.editsongform import SongFileEditForm, invalid_order_entries, lyrics_to_text, \
    order_to_text, text_to_lyrics, text_to_order, verse_tag_from_name
from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse
from openlp.plugins.filesystem_library.compat import QtWidgets


SONG = FileSong(titles=['Title', 'Alternate', 'Third'], authors=[('John', 'words+music'), ('Bob', '')],
                copyright='Public Domain', ccli_number='123', comments='Slowly\nquietly',
                songbooks=[('Hymnal', '12'), ('Notes', '')], topics=['Grace', 'Joy'], verse_order=['v1', 'c1', 'v2a'],
                verses=[SongVerse('v', '1', '', None, 'First\nverse'), SongVerse('c', '1', '', 'en', 'Chorus'),
                        SongVerse('v', '2', 'a', None, 'Second[--}{--]page')])


@pytest.fixture
def form(settings):
    form = SongFileEditForm()
    yield form
    form.deleteLater()


def test_lyrics_round_trip(settings):
    """The verses come back the same from the edited text"""
    text = lyrics_to_text(SONG.verses)

    assert text.startswith('---[Verse:1]---\nFirst\nverse\n---[Chorus:1:en]---\nChorus\n')
    assert text_to_lyrics(text) == SONG.verses


@pytest.mark.parametrize('text, expected', [
    ('Just text', [SongVerse('v', '1', '', None, 'Just text')]),
    ('Intro text\n---[Chorus:2]---\nChorus',
     [SongVerse('v', '1', '', None, 'Intro text'), SongVerse('c', '2', '', None, 'Chorus')]),
    ('---[c]---\nChorus\n\n', [SongVerse('c', '1', '', None, 'Chorus')]),
    ('---[Bridge:x]---\nB\r\n', [SongVerse('b', '1', '', None, 'B')]),
    ('---[Verse:1]---\nA\n---[Verse:1]---\nB', [SongVerse('v', '1', '', None, 'A\nB')]),
    ('---[Verse:1]---\n\n---[Verse:2]---\nB', [SongVerse('v', '2', '', None, 'B')]),
    ('---[Unknown:3]---\nX', [SongVerse('o', '3', '', None, 'X')]),
    ('   \n', []),
])
def test_text_to_lyrics(settings, text, expected):
    """Verse lines are understood loosely, and empty verses are dropped"""
    assert text_to_lyrics(text) == expected


@pytest.mark.parametrize('name, tag', [('Verse', 'v'), ('chorus', 'c'), ('Pre-Chorus', 'p'), ('pre', 'p'),
                                       ('e', 'e'), ('', 'o'), ('Something', 'o')])
def test_verse_tag_from_name(settings, name, tag):
    assert verse_tag_from_name(name) == tag


def test_verse_tag_from_translated_name(settings):
    """Translated verse names are understood before the English ones"""
    with patch.object(UiStrings(), 'Chorus', 'Kertosäe'), patch.object(UiStrings(), 'Verse', 'Säe'):
        assert verse_tag_from_name('kertosäe') == 'c'
        assert verse_tag_from_name('Säe') == 'v'
        assert verse_tag_from_name('Chorus') == 'c'


def test_order_round_trip(settings):
    """The verse order is shown with upper case tags and read back"""
    assert order_to_text(['v1', 'c', 'v2a']) == 'V1 C V2a'
    assert text_to_order('V1 C V2a') == (['v1', 'c', 'v2a'], [])


def test_text_to_order_invalid(settings):
    """Entries which are not verses are returned separately"""
    assert text_to_order('v1 x1 12 c') == (['v1', 'c'], ['x1', '12'])


def test_invalid_order_entries(settings):
    """The order may name a verse fully, by tag and number or by tag only"""
    assert invalid_order_entries(['v1', 'v2', 'v2a', 'c', 'b', 'c2'], SONG.verses) == ['b', 'c2']


def test_load_and_get_song(form):
    """The form gives back the song it was loaded with"""
    form.load_song(SONG)

    assert form.title_edit.text() == 'Title'
    assert form.verse_order_edit.text() == 'V1 C1 V2a'
    assert form.authors_list_view.topLevelItemCount() == 2
    assert form.songbooks_edit.toPlainText() == 'Hymnal #12\nNotes'
    assert form.get_song() == SONG


def test_new_song(form):
    """A new song starts with an empty first verse"""
    form.load_song(None)

    assert form.title_edit.text() == ''
    assert form.lyrics_edit.toPlainText() == '---[Verse:1]---\n'
    assert form.get_song() == FileSong()


def test_accept(form):
    """Saving a valid song closes the form and keeps the song"""
    form.load_song(SONG)
    form.title_edit.setText('  Changed ')

    with patch.object(QtWidgets.QDialog, 'accept') as mocked_accept:
        form.accept()

    mocked_accept.assert_called_once()
    assert form.song.titles == ['Changed', 'Alternate', 'Third']


@pytest.mark.parametrize('field, value', [('title_edit', ''), ('lyrics_edit', '---[Verse:1]---\n'),
                                          ('verse_order_edit', 'V1 B1'), ('verse_order_edit', 'V1 ?')])
def test_accept_invalid(form, field, value):
    """An invalid song is not accepted and the user is told why"""
    form.load_song(SONG)
    widget = getattr(form, field)
    widget.setPlainText(value) if isinstance(widget, QtWidgets.QPlainTextEdit) else widget.setText(value)

    with patch('openlp.plugins.song_folder.forms.editsongform.critical_error_message_box') as mocked_error, \
            patch.object(QtWidgets.QDialog, 'accept') as mocked_accept:
        form.accept()

    mocked_error.assert_called_once()
    mocked_accept.assert_not_called()
    assert form.song is None


def test_insert_verse(form):
    """A new verse gets the next free number of its type"""
    form.load_song(SONG)
    form.lyrics_edit.moveCursor(form.lyrics_edit.textCursor().MoveOperation.End)
    form.verse_type_combo_box.setCurrentIndex(0)

    form.on_insert_button_clicked()

    assert form.lyrics_edit.toPlainText().endswith('page\n---[Verse:3]---\n')


def test_authors(form):
    """Authors are added once with their type and can be removed"""
    form.load_song(None)
    form.author_name_edit.setText(' Jane ')
    form.author_type_combo_box.setCurrentIndex(2)

    form.on_author_add_button_clicked()
    form.add_author('Jane', 'music')
    form.add_author('Joe')

    assert form.get_song().authors == [('Jane', 'music'), ('Joe', '')]
    form.authors_list_view.topLevelItem(0).setSelected(True)
    form.on_author_remove_button_clicked()
    assert form.get_song().authors == [('Joe', '')]


def test_theme(form):
    """The theme of the song is chosen from the themes of OpenLP"""
    form.load_themes(['Light', 'Dark'])
    form.load_song(FileSong(titles=['Song'], verses=[SongVerse('v', text='Line')], theme='Dark'))

    assert form.theme_combo_box.currentText() == 'Dark'
    form.theme_combo_box.setCurrentIndex(0)
    assert form.get_song().theme == ''


def test_transpose(form, settings):
    """The chords of all the verses are transposed"""
    settings.setValue('songs/warn about missing song key', False)
    form.load_song(FileSong(titles=['Song'], verses=[SongVerse('v', text='[=C]Line [G]two'),
                                                     SongVerse('c', text='[F]Chorus')]))

    form.transpose(2)

    assert text_to_lyrics(form.lyrics_edit.toPlainText()) == [SongVerse('v', text='[=D]Line [A]two'),
                                                              SongVerse('c', text='[G]Chorus')]


def test_background_audio(form):
    """The audio file of the song is shown and can be removed"""
    form.load_song(SONG, Path('/songs/Title.mp3'))

    assert form.audio_path == Path('/songs/Title.mp3')
    assert form.audio_edit.text() == str(Path('/songs/Title.mp3'))
    assert form.audio_remove_button.isEnabled()

    form.audio_remove_button.click()

    assert form.audio_path is None
    assert form.audio_edit.text() == ''
    assert not form.audio_remove_button.isEnabled()


@patch('openlp.plugins.song_folder.forms.editsongform.FileDialog.getOpenFileName')
def test_choose_background_audio(mocked_dialog, form):
    """An audio file can be chosen for the song"""
    mocked_dialog.return_value = (Path('/music/new.ogg'), '')
    form.load_song(SONG)

    form.audio_choose_button.click()

    assert form.audio_path == Path('/music/new.ogg')
    mocked_dialog.return_value = (None, '')
    form.audio_choose_button.click()
    assert form.audio_path == Path('/music/new.ogg')


def test_load_song_clears_background_audio(form):
    """Loading another song forgets the audio of the previous song"""
    form.load_song(SONG, Path('/songs/Title.mp3'))
    form.load_song(SONG)

    assert form.audio_path is None
