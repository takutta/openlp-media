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
Test reading OpenLyrics files without a database
"""
from pathlib import Path

import pytest

from openlp.plugins.song_folder.lib.songfile import FileSong, SongFileError, SongVerse, normalise, parse_song_file, \
    parse_song_xml
from tests.utils.constants import RESOURCE_PATH


OPENLYRICS_PATH = RESOURCE_PATH / 'songs' / 'openlyrics'

SONG = '''<?xml version="1.0" encoding="UTF-8"?>
<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.9">
  <properties>
    <titles>
      <title>Herra kaikkialla</title>
      <title>Lord of all</title>
    </titles>
    <authors>
      <author type="words">Matti Meikäläinen</author>
      <author type="music">Matti Meikäläinen</author>
      <author type="translation">Liisa Laine</author>
      <author>Anonymous</author>
    </authors>
    <copyright>Public Domain</copyright>
    <ccliNo>1234567</ccliNo>
    <verseOrder>v1 c v2 x1 c</verseOrder>
    <songbooks>
      <songbook name="Virsikirja" entry="12"/>
      <songbook name="Notes"/>
    </songbooks>
    <themes>
      <theme>Ylistys</theme>
    </themes>
    <comments>
      <comment>Slowly</comment>
    </comments>
  </properties>
  <lyrics>
    <verse name="v1">
      <lines>
        First line<br/>
        second <chord name="G"/>line
      </lines>
    </verse>
    <verse name="c1">
      <lines break="optional">Chorus</lines>
      <lines>more chorus</lines>
    </verse>
    <verse name="v2">
      <lines>Page one<p style="page-break-after: always;"/>Page two</lines>
    </verse>
    <verse name="x1">
      <lines>Unknown tag</lines>
    </verse>
  </lyrics>
</song>
'''.encode('utf-8')


def test_parse_properties(settings):
    """The properties of the song are read without a database"""
    song = parse_song_xml(SONG)

    assert song.title == 'Herra kaikkialla'
    assert song.alternate_title == 'Lord of all'
    assert song.authors == [('Matti Meikäläinen', 'words+music'), ('Liisa Laine', 'translation'),
                            ('Anonymous', '')]
    assert song.copyright == 'Public Domain'
    assert song.ccli_number == '1234567'
    assert song.songbooks == [('Virsikirja', '12'), ('Notes', '')]
    assert song.songbook_entries == ['Virsikirja #12', 'Notes']
    assert song.topics == ['Ylistys']
    assert song.comments == 'Slowly'


def test_parse_lyrics(settings):
    """Line breaks, chords, optional splits and page breaks are converted like the Songs plugin does"""
    settings.setValue('songs/enable chords', True)
    settings.setValue('songs/disable chords import', False)

    song = parse_song_xml(SONG)

    assert [verse.name for verse in song.verses] == ['v1', 'c1', 'v2', 'o1']
    assert song.verses[0].text == 'First line\nsecond [G]line'
    assert song.verses[1].text == 'Chorus\n[---]\nmore chorus'
    assert song.verses[2].text == 'Page one[--}{--]Page two'
    # The unknown verse tag became "other", and the verse order follows it
    assert song.verse_order == ['v1', 'c', 'v2', 'o1', 'c']


def test_ordered_verses(settings):
    """The verse order picks verses by full name, by tag and number or by tag only"""
    song = FileSong(titles=['Song'], verses=[SongVerse('v', '1'), SongVerse('c', '1'), SongVerse('v', '2', 'a'),
                                             SongVerse('v', '2', 'b')],
                    verse_order=['v1', 'c', 'v2', 'v2b', 'missing'])

    assert [verse.name for verse in song.ordered_verses()] == ['v1', 'c1', 'v2a', 'v2b', 'v2b']


def test_ordered_verses_without_order(settings):
    """Without a verse order, the verses are in the order of the file"""
    song = FileSong(titles=['Song'], verses=[SongVerse('c', '1'), SongVerse('v', '1')])

    assert [verse.name for verse in song.ordered_verses()] == ['c1', 'v1']


def test_search_text(settings):
    """The search text has all the fields, without chords or punctuation"""
    text = parse_song_xml(SONG).search_text()

    for words in ('herra kaikkialla', 'lord of all', 'matti meikäläinen', 'liisa laine', 'public domain', '1234567',
                  'virsikirja 12', 'ylistys', 'slowly', 'second line', 'page two'):
        assert words in text
    assert 'g' not in text.split()


def test_normalise():
    """Punctuation, chords and formatting tags are removed and the case is folded"""
    assert normalise('{r}Hal-le[C]lu_jah!{/r}  AMEN') == 'hal lelu jah amen'


@pytest.mark.parametrize('file_name', ['Amazing Grace.xml', 'Amazing_Grace_1.xml', 'Amazing_Grace_2.xml',
                                       'What a friend we have in Jesus.xml', 'duchu-tags.xml'])
def test_parse_resource_files(settings, file_name):
    """The OpenLyrics test files of OpenLP can be read"""
    song = parse_song_file(OPENLYRICS_PATH / file_name)

    assert song.title
    assert song.verses
    assert all(verse.text for verse in song.verses)


def test_indentation_is_removed(settings):
    """Whitespace in the XML only separates words"""
    song = parse_song_file(OPENLYRICS_PATH / 'What a friend we have in Jesus.xml')

    assert song.authors == [('Joseph M. Scriven', ''), ('Charles C. Convers', '')]
    assert song.verses[0].text.split('\n')[:2] == [
        'What a friend we have in Jesus, All ours sins and griefs to bear;',
        'What a privilege to carry, Everything to God in prayer!']


def test_old_line_elements(settings):
    """OpenLyrics 0.7 uses a <line> element for each line"""
    xml = b'''<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.7">
      <properties><titles><title>Old</title></titles></properties>
      <lyrics><verse name="v1"><lines><line>One</line><line>Two</line></lines></verse></lyrics></song>'''

    assert parse_song_xml(xml).verses[0].text == 'One\nTwo'


@pytest.mark.parametrize('xml', [b'not xml', b'<song/>', b'<other><properties/></other>',
                                 b'<song><properties><titles/></properties><lyrics/></song>',
                                 b'<song><properties><titles><title>T</title></titles></properties></song>'])
def test_invalid_files(settings, xml):
    """Files which are not OpenLyrics songs raise SongFileError"""
    with pytest.raises(SongFileError):
        parse_song_xml(xml)


def test_missing_file():
    """A file which cannot be read raises SongFileError"""
    with pytest.raises(SongFileError):
        parse_song_file(Path('/does/not/exist.xml'))


def test_external_entities_are_not_loaded(settings, temp_folder):
    """The parser does not read other files through entities"""
    secret = Path(temp_folder) / 'secret.txt'
    secret.write_text('secret')
    xml = '''<?xml version="1.0"?>
    <!DOCTYPE song [<!ENTITY secret SYSTEM "file://{path}">]>
    <song xmlns="http://openlyrics.info/namespace/2009/song" version="0.8">
      <properties><titles><title>&secret;</title></titles></properties>
      <lyrics><verse name="v1"><lines>Text</lines></verse></lyrics></song>'''.format(path=secret.as_posix())

    try:
        song = parse_song_xml(xml.encode())
    except SongFileError:
        return
    assert 'secret' not in song.title
