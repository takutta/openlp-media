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
Test the edit form of the song folder plugin
"""
from unittest.mock import patch

import pytest

from openlp.plugins.song_folder.forms.editsongform import EditSongForm, parse_verse_order, text_to_verses, \
    verses_to_text
from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse


def test_verses_to_text_and_back():
    """The lyrics editor text keeps the verse types, labels and languages"""
    verses = [SongVerse('v', '1', text='One\ntwo'), SongVerse('c', '1', text='Chorus'),
              SongVerse('v', '2', 'a', 'fi', text='Kaksi')]

    text = verses_to_text(verses)

    assert text == '---[Verse:1]---\nOne\ntwo\n---[Chorus:1]---\nChorus\n---[Verse:2a:fi]---\nKaksi'
    assert text_to_verses(text) == verses


def test_text_to_verses_loose_input():
    """Text before the first header is the first verse, types are matched loosely and empty verses are dropped"""
    verses = text_to_verses('Intro text\n\n---[chorus:2]---\nSing\n\n---[Something:3]---\nOther\n---[Bridge:1]---\n\n')

    assert [(verse.name, verse.text) for verse in verses] == [('v1', 'Intro text'), ('c2', 'Sing'), ('o3', 'Other')]


def test_text_to_verses_invalid_label():
    with pytest.raises(ValueError):
        text_to_verses('---[Verse:first]---\nText')


def test_parse_verse_order():
    assert parse_verse_order(' V1  c1 Chorus2 b ') == ['v1', 'c1', 'c2', 'b']


FINNISH = ['Säe', 'Kertosäe', 'Bridge', 'Esikertosäe', 'Intro', 'Lopetus', 'Muu']


@patch('openlp.plugins.song_folder.forms.editsongform.verse_names', return_value=FINNISH)
def test_translated_verse_names(mocked_names):
    """Verse types can be written in the current language, both in the lyrics and in the verse order"""
    assert verses_to_text([SongVerse('c', '1', text='Text')]) == '---[Kertosäe:1]---\nText'
    assert [verse.name for verse in text_to_verses('---[kertosäe:2]---\nA\n---[Chorus:3]---\nB')] == ['c2', 'c3']
    assert parse_verse_order('s1 k1 kertosäe2 v2') == ['v1', 'c1', 'c2', 'v2']


@pytest.fixture
def form(settings):
    form = EditSongForm()
    yield form
    form.deleteLater()


def test_load_and_get_song(form):
    """A song read from the form is the song that was loaded"""
    song = FileSong(titles=['Title', 'Other title'], authors=[('Writer', 'words'), ('Someone', '')],
                    copyright='PD', ccli_number='42', comments='Note', songbooks=[('Book', '7')],
                    topics=['Grace', 'Joy'], verse_order=['v1', 'c1'],
                    verses=[SongVerse('v', '1', text='Verse'), SongVerse('c', '1', text='Chorus')])

    form.load_song(song)

    assert form.get_song() == song
    assert form.validate() == ''


def test_new_song_has_a_verse_header(form):
    """A new song starts with an empty first verse"""
    form.load_song(None)

    assert form.lyrics_edit.toPlainText() == '---[Verse:1]---\n'
    assert form.get_song().verses == []


@pytest.mark.parametrize('title, lyrics, order, error', [
    ('', '---[Verse:1]---\nText', '', 'title'),
    ('Title', '---[Verse:1]---\n', '', 'verse'),
    ('Title', '---[Verse:x]---\nText', '', 'label'),
    ('Title', '---[Verse:1]---\nText', 'v1 c1', 'c1'),
])
def test_validate(form, title, lyrics, order, error):
    """Missing titles and verses, bad labels and unknown verses in the verse order are reported"""
    form.load_song(None)
    form.title_edit.setText(title)
    form.lyrics_edit.setPlainText(lyrics)
    form.verse_order_edit.setText(order)

    assert error in form.validate()


@patch('openlp.plugins.song_folder.forms.editsongform.critical_error_message_box')
def test_accept_shows_error(mocked_error, form):
    """The form is not closed when the song is not valid"""
    form.load_song(None)
    form.accept()

    mocked_error.assert_called_once()
    assert form.result() == 0


def test_add_rows(form):
    """Empty rows of the tables are ignored"""
    form.load_song(None)
    form._add_row(form.authors_table, 'Writer', 'music')
    form._add_row(form.authors_table)
    form._add_row(form.songbooks_table, 'Book')

    assert form._table_rows(form.authors_table) == [('Writer', 'music')]
    assert form._table_rows(form.songbooks_table) == [('Book', '')]
