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
Test writing OpenLyrics files without a database
"""
import os
import stat
from pathlib import Path

import pytest
from lxml import etree

from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse, parse_song_file, parse_song_xml
from openlp.plugins.song_folder.lib.songwriter import new_song_path, song_to_xml, write_song_file
from tests.utils.constants import RESOURCE_PATH


NS = '{http://openlyrics.info/namespace/2009/song}'
ORIGINAL = b'''<?xml version="1.0" encoding="UTF-8"?>
<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.9" createdIn="Other App 1.0"
      chordNotation="german">
  <properties>
    <titles><title>Amazing &amp; Grace</title><title>Alternate</title><title>Third title</title></titles>
    <authors><author type="words">John</author><author type="music">John</author><author>Bob</author></authors>
    <tempo type="bpm">90</tempo>
    <key>G</key>
    <verseOrder>v1 c v2</verseOrder>
    <songbooks><songbook name="Book" entry="12"/></songbooks>
    <themes><theme>Grace</theme></themes>
  </properties>
  <format>
    <tags application="OpenLP">
      <tag name="r"><open>&lt;span style="color:red"&gt;</open><close>&lt;/span&gt;</close></tag>
      <tag name="unused"><open>&lt;b&gt;</open><close>&lt;/b&gt;</close></tag>
    </tags>
  </format>
  <lyrics>
    <verse name="v1">
      <lines><chord name="G"/>Amazing <tag name="r">grace</tag><br/>how sweet</lines>
      <lines>second part</lines>
    </verse>
    <verse name="c1" lang="en"><lines>Chorus<p style="page-break-after: always;"/>page two</lines></verse>
    <verse name="v2"><lines>Two &amp; three</lines></verse>
  </lyrics>
  <custom xmlns="urn:example">keep me</custom>
</song>'''


@pytest.fixture
def chords(settings):
    settings.setValue('songs/enable chords', True)
    settings.setValue('songs/disable chords import', False)


def test_round_trip_keeps_the_song(chords):
    """Writing a song and reading it again gives the same song"""
    song = parse_song_xml(ORIGINAL)

    assert parse_song_xml(song_to_xml(song, ORIGINAL)) == song


def test_round_trip_without_original(chords):
    """A song can be written without an original file"""
    song = parse_song_xml(ORIGINAL)

    assert parse_song_xml(song_to_xml(song)) == song


def test_unknown_parts_of_the_original_are_kept(chords):
    """What the editor does not know about is copied from the original file"""
    # GIVEN: A song read from a file, with a changed title
    song = parse_song_xml(ORIGINAL)
    song.titles[0] = 'New title'

    # WHEN: Writing it
    xml = etree.fromstring(song_to_xml(song, ORIGINAL))

    # THEN: The other properties, the formatting tags and the unknown elements are still there
    properties = xml.find(NS + 'properties')
    assert [title.text for title in properties.find(NS + 'titles')] == ['New title', 'Alternate', 'Third title']
    assert properties.find(NS + 'tempo').text == '90'
    assert properties.find(NS + 'tempo').get('type') == 'bpm'
    assert properties.find(NS + 'key').text == 'G'
    assert [tag.get('name') for tag in xml.find(NS + 'format').find(NS + 'tags')] == ['r', 'unused']
    assert xml.find('{urn:example}custom').text == 'keep me'
    assert xml.get('createdIn') == 'Other App 1.0'
    assert xml.get('chordNotation') == 'german'
    assert xml.get('modifiedIn').startswith('OpenLP')
    # The properties written from the song are not doubled
    assert len(properties.findall(NS + 'authors')) == 1
    assert len(properties.findall(NS + 'verseOrder')) == 1


def test_removed_properties_are_removed(settings):
    """A property that was cleared in the editor is not copied from the original"""
    song = parse_song_xml(ORIGINAL)
    song.topics = []
    song.songbooks = []

    properties = etree.fromstring(song_to_xml(song, ORIGINAL)).find(NS + 'properties')

    assert properties.find(NS + 'themes') is None
    assert properties.find(NS + 'songbooks') is None


def test_original_without_namespace(settings):
    """Elements copied from a file without the OpenLyrics namespace are moved into it"""
    original = b'<song version="0.8"><properties><titles><title>A</title></titles><key>D</key></properties>' \
               b'<lyrics><verse name="v1"><lines>x</lines></verse></lyrics></song>'

    xml = etree.fromstring(song_to_xml(parse_song_xml(original), original))

    assert xml.find(NS + 'properties').find(NS + 'key').text == 'D'


def test_broken_original_is_ignored(settings):
    """The song is still written if the original file is not valid XML"""
    song = FileSong(titles=['Song'], verses=[SongVerse('v', text='Line')])

    assert parse_song_xml(song_to_xml(song, b'not xml')) == song


def test_authors_of_both_words_and_music(settings):
    """An author of both words and music is written twice, as OpenLyrics wants"""
    song = FileSong(titles=['Song'], authors=[('John', 'words+music')], verses=[SongVerse('v', text='Line')])

    authors = etree.fromstring(song_to_xml(song)).find(NS + 'properties').find(NS + 'authors')

    assert [(author.text, author.get('type')) for author in authors] == [('John', 'words'), ('John', 'music')]
    assert parse_song_xml(song_to_xml(song)).authors == [('John', 'words+music')]


def test_verses_with_parts_and_splits(settings):
    """Verse parts, optional splits and page breaks are written"""
    song = FileSong(titles=['Song'], verse_order=['v1', 'v1b'],
                    verses=[SongVerse('v', '1', 'a', None, 'One\n[---]\nTwo'),
                            SongVerse('v', '1', 'b', None, 'Three[--}{--]Four')])

    assert parse_song_xml(song_to_xml(song)) == song


def test_trailing_optional_split_is_dropped(settings):
    """An optional split at the end of a verse is not written as text"""
    song = FileSong(titles=['Song'], verses=[SongVerse('v', text='Line\n[---]')])

    assert parse_song_xml(song_to_xml(song)).verses[0].text == 'Line'


OPENLYRICS_FILES = sorted(path.name for path in (RESOURCE_PATH / 'songs' / 'openlyrics').glob('*.xml'))


@pytest.mark.parametrize('file_name', OPENLYRICS_FILES)
def test_resource_files_survive_a_round_trip(settings, file_name):
    """The OpenLyrics files of the tests of the Songs plugin are read back the same after writing them"""
    original = (RESOURCE_PATH / 'songs' / 'openlyrics' / file_name).read_bytes()
    try:
        song = parse_song_xml(original)
    except Exception:
        pytest.skip('Not a song this plugin can read')

    assert parse_song_xml(song_to_xml(song, original)) == song


def test_write_song_file(settings, temp_folder):
    """The file is written and no temporary file is left behind"""
    file_path = Path(temp_folder) / 'song.xml'
    file_path.write_bytes(ORIGINAL)
    os.chmod(file_path, 0o640)
    song = parse_song_xml(ORIGINAL)
    song.titles[0] = 'Changed'

    write_song_file(song, file_path, ORIGINAL)

    assert parse_song_file(file_path).title == 'Changed'
    assert os.listdir(temp_folder) == ['song.xml']
    assert stat.S_IMODE(file_path.stat().st_mode) == 0o640


def test_write_song_file_failure_keeps_the_old_file(settings, temp_folder):
    """A failed write leaves the old file as it was"""
    file_path = Path(temp_folder) / 'song.xml'
    file_path.write_bytes(ORIGINAL)
    song = parse_song_xml(ORIGINAL)

    with pytest.raises(OSError):
        write_song_file(song, Path(temp_folder) / 'missing' / 'song.xml')

    assert file_path.read_bytes() == ORIGINAL
    assert os.listdir(temp_folder) == ['song.xml']


@pytest.mark.parametrize('title, expected', [('Amazing Grace', 'Amazing Grace.xml'),
                                             ('What? / Why: "now"', 'What_ _ Why_ _now_.xml'),
                                             ('...', 'Song.xml'),
                                             ('', 'Song.xml')])
def test_new_song_path(temp_folder, title, expected):
    """The file name comes from the title, without characters that are not allowed in file names"""
    assert new_song_path(Path(temp_folder), title) == Path(temp_folder) / expected


def test_new_song_path_does_not_overwrite(temp_folder):
    """A number is added if the file exists already"""
    (Path(temp_folder) / 'Song.xml').write_text('')
    (Path(temp_folder) / 'Song (2).xml').write_text('')

    assert new_song_path(Path(temp_folder), 'Song') == Path(temp_folder) / 'Song (3).xml'
