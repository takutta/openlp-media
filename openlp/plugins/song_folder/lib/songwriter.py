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
Writes songs to OpenLyrics files without a database. When a file is saved again, only the parts which OpenLP edits are
replaced, so that everything else in the file (tempo, key, publisher, comments in the lyrics etc.) is kept.
"""
import html
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from lxml import etree

from openlp.core.version import get_version
from openlp.plugins.song_folder.lib.songfile import OPENLP_NAMESPACE, THEME_TAG, FileSong, SongFileError
from openlp.plugins.songs.lib.openlyricsxml import NAMESPACE, OpenLyrics


OPENLYRICS_VERSION = '0.9'
# The order of the elements in <properties>, from the OpenLyrics schema
PROPERTY_ORDER = ['titles', 'authors', 'copyright', 'ccliNo', 'releaseDate', 'transposition', 'tempo', 'key',
                  'variant', 'publisher', 'version', 'keywords', 'verseOrder', 'songbooks', 'themes', 'comments']
# The properties which are edited in OpenLP, everything else is kept as it is
EDITED_PROPERTIES = ['titles', 'authors', 'copyright', 'ccliNo', 'verseOrder', 'songbooks', 'themes', 'comments']
# Characters which are not allowed in file names on some operating systems
_BAD_FILE_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# An optional split at the end of a verse, which would be written as text
_TRAILING_SPLIT = re.compile(r'(\n\[---\])+\s*$')
# Do not load anything from outside the file
_parser = etree.XMLParser(remove_blank_text=True, resolve_entities=False, no_network=True)


def _tag(name: str) -> str:
    return '{{{namespace}}}{name}'.format(namespace=NAMESPACE, name=name)


def _sub_element(parent, tag_name: str, text: Optional[str] = None, **attributes):
    element = etree.SubElement(parent, _tag(tag_name), **attributes)
    if text:
        element.text = text
    return element


def _properties_element(song: FileSong):
    """
    Build the <properties> element with the fields OpenLP edits
    """
    properties = etree.Element(_tag('properties'))
    titles = _sub_element(properties, 'titles')
    for title in song.titles:
        _sub_element(titles, 'title', title)
    if song.authors:
        authors = _sub_element(properties, 'authors')
        for name, author_type in song.authors:
            # OpenLyrics has no "words+music" type, so somebody who wrote both is listed twice
            if author_type == 'words+music':
                _sub_element(authors, 'author', name, type='words')
                _sub_element(authors, 'author', name, type='music')
            elif author_type:
                _sub_element(authors, 'author', name, type=author_type)
            else:
                _sub_element(authors, 'author', name)
    if song.copyright:
        _sub_element(properties, 'copyright', song.copyright)
    if song.ccli_number:
        _sub_element(properties, 'ccliNo', song.ccli_number)
    if song.verse_order:
        _sub_element(properties, 'verseOrder', ' '.join(song.verse_order))
    if song.songbooks:
        songbooks = _sub_element(properties, 'songbooks')
        for book, entry in song.songbooks:
            if entry:
                _sub_element(songbooks, 'songbook', name=book, entry=entry)
            else:
                _sub_element(songbooks, 'songbook', name=book)
    if song.topics:
        themes = _sub_element(properties, 'themes')
        for topic in song.topics:
            _sub_element(themes, 'theme', topic)
    if song.comments:
        comments = _sub_element(properties, 'comments')
        for comment in song.comments.split('\n'):
            if comment.strip():
                _sub_element(comments, 'comment', comment.strip())
    return properties


def _lyrics_elements(song: FileSong):
    """
    Build the <lyrics> and <format> elements. The conversion of chords, formatting tags and line breaks is done with
    the code of the Songs plugin, so the result is the same as when the Songs plugin exports a song.

    :return: A tuple of (lyrics element, format element or None)
    """
    open_lyrics = OpenLyrics(None)
    # The Songs plugin builds the elements without a namespace, and the namespace is added when parsing them again
    format_element = etree.Element('format')
    tags_element = etree.SubElement(format_element, 'tags', application='OpenLP')
    lyrics = etree.Element('lyrics')
    for verse in song.verses:
        verse_element = etree.SubElement(lyrics, 'verse', name=verse.name)
        if verse.lang:
            verse_element.set('lang', verse.lang)
        parts = html.escape(_TRAILING_SPLIT.sub('', verse.text)).split('\n[---]\n')
        start_tags = ''
        for index, part in enumerate(parts):
            # Close the formatting tags in each part and open them again in the next one
            part = start_tags + part
            start_tags, end_tags = open_lyrics._get_missing_tags(part)
            part = open_lyrics._chordpro_to_openlyrics(part + end_tags)
            lines_element = open_lyrics._add_text_with_tags_to_lines(verse_element, part, tags_element)
            if index < len(parts) - 1:
                lines_element.set('break', 'optional')
    for element in (lyrics, format_element):
        for node in element.iter():
            if isinstance(node.tag, str) and not node.tag.startswith('{'):
                node.tag = _tag(node.tag)
    return lyrics, format_element if len(tags_element) else None


def _replace_property(properties, new_element, name: str):
    """
    Put the new version of a property in place of the old one, or in the right place if it is new
    """
    old_elements = properties.findall(_tag(name))
    if old_elements:
        position = properties.index(old_elements[0])
        for old_element in old_elements:
            properties.remove(old_element)
    else:
        position = 0
        earlier = PROPERTY_ORDER[:PROPERTY_ORDER.index(name)]
        for index, child in enumerate(properties):
            if isinstance(child.tag, str) and etree.QName(child).localname in earlier:
                position = index + 1
    if new_element is not None:
        properties.insert(position, new_element)


def song_to_xml(song: FileSong, original_xml: Optional[bytes] = None) -> bytes:
    """
    Convert a song to OpenLyrics

    :param song: The song
    :param original_xml: The current contents of the file, whose other contents are kept
    :return: The XML
    """
    application_name = 'OpenLP ' + get_version()['version']
    root = None
    if original_xml:
        try:
            root = etree.fromstring(original_xml, _parser)
        except etree.XMLSyntaxError:
            # Nothing can be kept from a broken file, but the song can still be saved
            root = None
        if root is not None and root.tag == 'song':
            # Some programs leave out the namespace, move the file into it
            for node in root.iter():
                if isinstance(node.tag, str) and etree.QName(node).namespace is None:
                    node.tag = _tag(node.tag)
        if root is not None and root.tag != _tag('song'):
            root = None
    if root is None:
        root = etree.Element(_tag('song'), nsmap={None: NAMESPACE})
        root.set('createdIn', application_name)
    root.set('version', OPENLYRICS_VERSION)
    root.set('modifiedIn', application_name)
    root.set('modifiedDate', datetime.now().astimezone().isoformat(timespec='seconds'))
    new_properties = _properties_element(song)
    properties = root.find(_tag('properties'))
    if properties is None:
        root.insert(0, new_properties)
    else:
        for name in EDITED_PROPERTIES:
            _replace_property(properties, new_properties.find(_tag(name)), name)
    # The theme comes after the lyrics, in the namespace of OpenLP
    for old_theme in root.findall(THEME_TAG):
        root.remove(old_theme)
    lyrics, format_element = _lyrics_elements(song)
    old_lyrics = root.find(_tag('lyrics'))
    if old_lyrics is not None:
        old_lyrics.getparent().replace(old_lyrics, lyrics)
    else:
        root.append(lyrics)
    # Keep the formatting tags of the file, and add the ones the lyrics use now
    if format_element is not None:
        old_format = root.find(_tag('format'))
        if old_format is None:
            root.insert(root.index(lyrics), format_element)
        else:
            old_tags = old_format.find(_tag('tags'))
            if old_tags is None:
                old_format.append(format_element.find(_tag('tags')))
            else:
                known = {tag.get('name') for tag in old_tags.findall(_tag('tag'))}
                for tag in format_element.find(_tag('tags')).findall(_tag('tag')):
                    if tag.get('name') not in known:
                        old_tags.append(tag)
    if song.theme:
        etree.SubElement(root, THEME_TAG, nsmap={'openlp': OPENLP_NAMESPACE}).text = song.theme
    # Indent the file, but not the lyrics: whitespace in <lines> is part of the text for other programs
    saved = [(node, node.text, node.tail) for lines in root.iter(_tag('lines')) for node in lines.iter()]
    etree.indent(root, space='  ')
    for node, text, tail in saved:
        node.text = text
        if node.tag != _tag('lines'):
            node.tail = tail
    return etree.tostring(root, encoding='UTF-8', xml_declaration=True, pretty_print=True)


def write_song_file(song: FileSong, file_path: Path, keep_contents: bool = True):
    """
    Save a song to a file. The file is replaced in one go, so it is never left half written.

    :param song: The song
    :param file_path: The file to write
    :param keep_contents: Keep the parts of an existing file which OpenLP does not edit
    :raises SongFileError: If the file cannot be written
    """
    original_xml = None
    if keep_contents and file_path.exists():
        try:
            original_xml = file_path.read_bytes()
        except OSError as error:
            raise SongFileError(str(error)) from error
    xml = song_to_xml(song, original_xml)
    try:
        handle, temp_name = tempfile.mkstemp(dir=file_path.parent, prefix='.', suffix='.tmp')
        try:
            with os.fdopen(handle, 'wb') as temp_file:
                temp_file.write(xml)
            if file_path.exists():
                os.chmod(temp_name, file_path.stat().st_mode)
            else:
                # mkstemp makes the file readable only by its owner
                umask = os.umask(0)
                os.umask(umask)
                os.chmod(temp_name, 0o666 & ~umask)
            os.replace(temp_name, file_path)
        except BaseException:
            Path(temp_name).unlink(missing_ok=True)
            raise
    except OSError as error:
        raise SongFileError(str(error)) from error


def song_file_name(title: str, folder: Path) -> Path:
    """
    Make a file name for a new song from its title, without overwriting an existing file

    :param title: The title of the song
    :param folder: The folder of the new file
    """
    name = _BAD_FILE_NAME_CHARS.sub('_', title).strip(' .') or 'song'
    file_path = folder / '{name}.xml'.format(name=name)
    number = 2
    while file_path.exists():
        file_path = folder / '{name} ({number}).xml'.format(name=name, number=number)
        number += 1
    return file_path
