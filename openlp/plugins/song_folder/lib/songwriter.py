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
Writes songs to OpenLyrics files without a database. The XML is made by the OpenLyrics export of the Songs plugin, and
everything in the original file that the editor does not know about is kept: other properties (tempo, key, publisher
etc.), formatting tag definitions, extra titles and the attributes of the song.
"""
import os
import re
import tempfile
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Optional

from lxml import etree

from openlp.plugins.songs.lib.openlyricsxml import NAMESPACE, SongXML
from openlp.plugins.song_folder.lib.songfile import FileSong, _helper


# The properties that come from the song, everything else is copied from the original file
SONG_PROPERTIES = {'titles', 'authors', 'copyright', 'ccliNo', 'comments', 'songbooks', 'themes', 'verseOrder'}
# The attributes of <song> that describe the new file
NEW_ATTRIBUTES = {'version', 'modifiedIn', 'modifiedDate'}
_parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)
_UNSAFE_FILE_NAME = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')
_TRAILING_SPLIT = re.compile(r'(\n\[---\])+\s*$')


def _tag(name: str) -> str:
    return '{{{namespace}}}{name}'.format(namespace=NAMESPACE, name=name)


def _local_name(element) -> Optional[str]:
    """
    The name of an element without its namespace, or None for comments and processing instructions
    """
    return etree.QName(element).localname if isinstance(element.tag, str) else None


def _child(element, name: str):
    """
    Returns the first child of an element with a name, in any namespace
    """
    if element is None:
        return None
    return next((child for child in element if _local_name(child) == name), None)


def _to_namespace(element):
    """
    Move an element copied from a file without the OpenLyrics namespace into it
    """
    for node in element.iter():
        if isinstance(node.tag, str) and etree.QName(node).namespace is None:
            node.tag = _tag(etree.QName(node).localname)
    return element


def _song_to_record(song: FileSong) -> SimpleNamespace:
    """
    Turn a song into an object that looks like a song in the database of the Songs plugin, for its OpenLyrics export
    """
    lyrics = SongXML()
    for verse in song.verses:
        # An optional split at the end would be written as text
        text = _TRAILING_SPLIT.sub('', verse.text)
        lyrics.add_verse_to_lyrics(verse.tag, verse.number + verse.part, text, verse.lang)
    return SimpleNamespace(
        title=song.title,
        alternate_title=song.alternate_title,
        comments=song.comments,
        copyright=song.copyright,
        verse_order=' '.join(song.verse_order),
        ccli_number=song.ccli_number,
        authors_songs=[SimpleNamespace(author=SimpleNamespace(display_name=name), author_type=author_type)
                       for name, author_type in song.authors],
        songbook_entries=[SimpleNamespace(songbook=SimpleNamespace(name=book), entry=entry)
                          for book, entry in song.songbooks],
        topics=[SimpleNamespace(name=topic) for topic in song.topics],
        lyrics=lyrics.extract_xml().decode('utf-8'),
        last_modified=datetime.now().replace(microsecond=0)
    )


def _merge_original(song_xml, original_xml):
    """
    Copy what the song does not describe from the original file into the new XML

    :param song_xml: The root of the new XML
    :param original_xml: The root of the original file
    """
    for name, value in original_xml.attrib.items():
        if name not in NEW_ATTRIBUTES:
            song_xml.set(name, value)
    properties = _child(song_xml, 'properties')
    for element in _child(original_xml, 'properties') if _child(original_xml, 'properties') is not None else []:
        if _local_name(element) and _local_name(element) not in SONG_PROPERTIES:
            properties.append(_to_namespace(deepcopy(element)))
    # Keep the definitions of the formatting tags, also the ones which are not used any more
    original_format = _child(original_xml, 'format')
    if original_format is not None:
        format_ = _child(song_xml, 'format')
        if format_ is None:
            song_xml.insert(song_xml.index(_child(song_xml, 'lyrics')), _to_namespace(deepcopy(original_format)))
        else:
            tags = _child(format_, 'tags')
            known = {tag.get('name') for tag in tags}
            for original_tags in original_format:
                for tag in original_tags if _local_name(original_tags) == 'tags' else []:
                    if _local_name(tag) == 'tag' and tag.get('name') not in known:
                        tags.append(_to_namespace(deepcopy(tag)))
                        known.add(tag.get('name'))
    # Anything else the song has, e.g. elements of other applications
    for element in original_xml:
        if _local_name(element) and _local_name(element) not in ('properties', 'format', 'lyrics'):
            song_xml.append(_to_namespace(deepcopy(element)))


def song_to_xml(song: FileSong, original: Optional[bytes] = None) -> bytes:
    """
    Convert a song to OpenLyrics

    :param song: The song
    :param original: The contents of the file the song was read from. What the song does not describe is kept.
    :return: The contents of the OpenLyrics file
    """
    xml = _helper().song_to_xml(_song_to_record(song))
    song_xml = etree.fromstring(xml.encode('utf-8'), _parser)
    titles = _child(_child(song_xml, 'properties'), 'titles')
    for title in song.titles[2:]:
        etree.SubElement(titles, _tag('title')).text = title
    if original:
        try:
            original_xml = etree.fromstring(original, _parser)
        except etree.XMLSyntaxError:
            original_xml = None
        if original_xml is not None:
            _merge_original(song_xml, original_xml)
    return etree.tostring(song_xml, encoding='UTF-8', xml_declaration=True, pretty_print=True)


def write_song_file(song: FileSong, file_path: Path, original: Optional[bytes] = None):
    """
    Write a song to an OpenLyrics file. The file is replaced in one go, so a failed write does not leave half a song.

    :param song: The song
    :param file_path: The file to write
    :param original: The contents of the file the song was read from, see :func:`song_to_xml`
    :raises OSError: If the file cannot be written
    """
    xml = song_to_xml(song, original)
    # The temporary file is hidden, so that the library does not list it
    handle, temp_name = tempfile.mkstemp(prefix='.', suffix='.tmp', dir=file_path.parent)
    try:
        with os.fdopen(handle, 'wb') as temp_file:
            temp_file.write(xml)
        if file_path.exists():
            os.chmod(temp_name, file_path.stat().st_mode & 0o777)
        else:
            # mkstemp makes the file readable only by its owner
            umask = os.umask(0)
            os.umask(umask)
            os.chmod(temp_name, 0o666 & ~umask)
        os.replace(temp_name, file_path)
    except BaseException:
        if os.path.exists(temp_name):
            os.remove(temp_name)
        raise


def new_song_path(folder: Path, title: str) -> Path:
    """
    Returns a path in a folder for a new song, named after its title. Existing files are not overwritten.

    :param folder: The folder of the song
    :param title: The title of the song
    """
    name = _UNSAFE_FILE_NAME.sub('_', title).strip().strip('.').strip() or 'Song'
    name = name[:100].strip()
    file_path = folder / '{name}.xml'.format(name=name)
    number = 2
    while file_path.exists():
        file_path = folder / '{name} ({number}).xml'.format(name=name, number=number)
        number += 1
    return file_path
