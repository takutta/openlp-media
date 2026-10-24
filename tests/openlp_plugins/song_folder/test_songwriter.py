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
from pathlib import Path
from unittest.mock import patch

import pytest
from lxml import etree

from openlp.plugins.song_folder.lib.songfile import FileSong, SongFileError, SongVerse, parse_song_file, \
    parse_song_xml
from openlp.plugins.song_folder.lib.songwriter import song_file_name, song_to_xml, split_names, write_song_file
from openlp.plugins.songs.lib.openlyricsxml import NAMESPACE


def make_song() -> FileSong:
    return FileSong(titles=['Herra kaikkialla', 'Lord of all'],
                    authors=[('Matti Meikäläinen', 'words+music'), ('Liisa Laine', 'translation'), ('Anon', '')],
                    copyright='Public Domain', ccli_number='123', comments='Slowly\nQuietly',
                    songbooks=[('Virsikirja', '12'), ('Notes', '')], topics=['Ylistys', 'Kiitos'],
                    verse_order=['v1', 'c1', 'v1'],
                    verses=[SongVerse('v', '1', text='First & line\nsecond [G]line'),
                            SongVerse('c', '1', text='{r}Red\n[---]\nstill red{/r}'),
                            SongVerse('v', '2', 'a', 'fi', text='Page one[--}{--]Page two')])


def test_round_trip(settings):
    """A written song reads back the same"""
    settings.setValue('songs/enable chords', True)
    song = make_song()

    result = parse_song_xml(song_to_xml(song))

    assert result.titles == song.titles
    assert result.authors == song.authors
    assert result.copyright == song.copyright
    assert result.ccli_number == song.ccli_number
    assert result.comments == song.comments
    assert result.songbooks == song.songbooks
    assert result.topics == song.topics
    assert result.verse_order == song.verse_order
    assert [(verse.name, verse.lang, verse.text) for verse in result.verses] == [
        ('v1', None, 'First & line\nsecond [G]line'),
        # Formatting tags are closed in each part and opened again in the next one
        ('c1', None, '{r}Red{/r}\n[---]\n{r}still red{/r}'),
        ('v2a', 'fi', 'Page one[--}{--]Page two')]


def test_xml_structure(settings):
    """The XML uses the OpenLyrics namespace, lists "words+music" authors twice and declares formatting tags"""
    root = etree.fromstring(song_to_xml(make_song()))
    ns = {'ol': NAMESPACE}

    assert root.tag == '{{{ns}}}song'.format(ns=NAMESPACE)
    assert root.get('version') == '0.9'
    assert [(a.text, a.get('type')) for a in root.findall('ol:properties/ol:authors/ol:author', ns)][:2] == [
        ('Matti Meikäläinen', 'words'), ('Matti Meikäläinen', 'music')]
    assert root.find('ol:format/ol:tags/ol:tag[@name="r"]', ns) is not None
    assert root.find('ol:lyrics/ol:verse/ol:lines/ol:chord', ns).get('name') == 'G'
    # Every element is in the OpenLyrics namespace
    assert all(element.tag.startswith('{' + NAMESPACE) for element in root.iter() if isinstance(element.tag, str))


def test_lyrics_are_not_indented(settings):
    """Other programs read whitespace in <lines> as text, so the lyrics are written without indentation"""
    xml = song_to_xml(make_song()).decode()

    assert '<lines>First &amp; line<br/>second <chord name="G"/>line</lines>' in xml


ORIGINAL = '''<?xml version="1.0" encoding="UTF-8"?>
<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.8" createdIn="Other App">
  <properties>
    <titles><title>Old title</title></titles>
    <copyright>Old</copyright>
    <tempo type="bpm">90</tempo>
    <key>G</key>
    <publisher>Some Publisher</publisher>
    <themes><theme>Old topic</theme></themes>
  </properties>
  <format><tags application="Other"><tag name="x"><open>&lt;b&gt;</open><close>&lt;/b&gt;</close></tag></tags></format>
  <lyrics><verse name="v1"><lines>Old text</lines></verse></lyrics>
</song>'''.encode()


def test_unknown_fields_are_kept(settings):
    """Saving a song again keeps the parts of the file that OpenLP does not edit"""
    song = FileSong(titles=['New title'], verse_order=['v1'], verses=[SongVerse('v', '1', text='{r}New{/r} text')],
                    authors=[('Writer', '')])

    root = etree.fromstring(song_to_xml(song, ORIGINAL))
    ns = {'ol': NAMESPACE}
    properties = [etree.QName(child).localname for child in root.find('ol:properties', ns)]

    # The edited fields are replaced, removed or added in the order of the schema, the others are kept
    assert properties == ['titles', 'authors', 'tempo', 'key', 'publisher', 'verseOrder']
    assert root.find('ol:properties/ol:tempo', ns).text == '90'
    assert root.find('ol:properties/ol:titles/ol:title', ns).text == 'New title'
    assert root.get('createdIn') == 'Other App'
    assert root.get('modifiedIn').startswith('OpenLP')
    # The formatting tags of the file are kept and the new ones are added
    assert [tag.get('name') for tag in root.findall('ol:format/ol:tags/ol:tag', ns)] == ['x', 'r']
    assert parse_song_xml(etree.tostring(root)).verses[0].text == '{r}New{/r} text'


def test_original_which_is_not_a_song(settings):
    """A file which is not an OpenLyrics song is written from scratch"""
    song = FileSong(titles=['Title'], verses=[SongVerse('v', '1', text='Text')])

    assert parse_song_xml(song_to_xml(song, b'<html/>')).title == 'Title'
    with pytest.raises(SongFileError):
        song_to_xml(song, b'not xml')


def test_write_song_file(settings, temp_folder):
    """The file is written, and no temporary files are left behind"""
    folder = Path(temp_folder)
    file_path = folder / 'song.xml'
    file_path.write_bytes(ORIGINAL)

    write_song_file(make_song(), file_path)

    assert parse_song_file(file_path).title == 'Herra kaikkialla'
    assert b'<tempo' in file_path.read_bytes()
    assert [path.name for path in folder.iterdir()] == ['song.xml']


def test_write_song_file_failure_keeps_old_file(settings, temp_folder):
    """When writing fails, the old file stays as it was"""
    file_path = Path(temp_folder) / 'song.xml'
    file_path.write_bytes(ORIGINAL)

    with patch('openlp.plugins.song_folder.lib.songwriter.os.replace', side_effect=OSError('disk full')):
        with pytest.raises(SongFileError):
            write_song_file(make_song(), file_path)

    assert file_path.read_bytes() == ORIGINAL
    assert [path.name for path in Path(temp_folder).iterdir()] == ['song.xml']


def test_song_file_name(temp_folder):
    """New file names come from the title, without overwriting files"""
    folder = Path(temp_folder)
    assert song_file_name('Herra: kaikkialla?', folder) == folder / 'Herra_ kaikkialla_.xml'
    assert song_file_name(' ... ', folder) == folder / 'song.xml'
    (folder / 'Song.xml').write_text('')
    (folder / 'Song (2).xml').write_text('')
    assert song_file_name('Song', folder) == folder / 'Song (3).xml'


def test_split_names():
    assert split_names(' Ylistys,, Kiitos ,') == ['Ylistys', 'Kiitos']
