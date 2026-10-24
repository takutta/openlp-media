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
Reads OpenLyrics files without a database. The Songs plugin can only read OpenLyrics into its database, so this module
parses a file into a plain :class:`FileSong` object instead. The line handling of the Songs plugin is reused, so that
chords, formatting tags and line breaks are converted in the same way.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from lxml import etree, objectify

from openlp.plugins.songs.lib import VerseType
from openlp.plugins.songs.lib.openlyricsxml import NAMESPACE, OpenLyrics


# The helper methods of OpenLyrics that are used here do not touch the database. It is created on first use, because
# its constructor loads the formatting tags from the settings.
_open_lyrics: Optional[OpenLyrics] = None
# Do not load anything from outside the file
_parser = objectify.makeparser(remove_blank_text=True, resolve_entities=False, no_network=True)
# Chords and formatting tags, which are left out of the search text
_MARKUP = re.compile(r'\[[^\]]*\]|\{/?[^}]*\}')
_NON_WORD = re.compile(r'[\W_]+')
_WHITESPACE = re.compile(r'\s+')
# A forced page break in the lyrics, created from <p style="page-break-after: always;"/>
FORCED_SPLIT = re.compile(r'\[--\}\{--\]\n?')


class SongFileError(Exception):
    """
    The file is not a valid OpenLyrics song
    """
    pass


def normalise(text: str) -> str:
    """
    Turn text into lower case words separated by single spaces, for searching

    :param text: The text to normalise
    """
    return _NON_WORD.sub(' ', _MARKUP.sub('', text)).casefold().strip()


@dataclass
class SongVerse:
    tag: str
    number: str = '1'
    part: str = ''
    lang: Optional[str] = None
    text: str = ''

    @property
    def name(self) -> str:
        """
        The name of the verse as used in the verse order, e.g. "v1"
        """
        return self.tag + self.number + self.part


@dataclass
class FileSong:
    titles: List[str] = field(default_factory=list)
    # (display name, author type) pairs, the types are the ones of AuthorType
    authors: List[Tuple[str, str]] = field(default_factory=list)
    copyright: str = ''
    ccli_number: str = ''
    comments: str = ''
    # (songbook name, entry) pairs
    songbooks: List[Tuple[str, str]] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    verse_order: List[str] = field(default_factory=list)
    verses: List[SongVerse] = field(default_factory=list)

    @property
    def title(self) -> str:
        return self.titles[0] if self.titles else ''

    @property
    def alternate_title(self) -> str:
        return self.titles[1] if len(self.titles) > 1 else ''

    @property
    def songbook_entries(self) -> List[str]:
        """
        The songbooks in the form "Book #12"
        """
        return ['{book} #{entry}'.format(book=book, entry=entry) if entry else book for book, entry in self.songbooks]

    def ordered_verses(self) -> List[SongVerse]:
        """
        The verses in the order they are shown. An entry of the verse order matches a verse by its full name ("v1a"),
        by its tag and number ("v1", all parts) or by its tag only ("c", all choruses). Without a usable verse order
        the verses are shown in the order of the file.
        """
        ordered = []
        for entry in self.verse_order:
            ordered.extend(verse for verse in self.verses
                           if entry in (verse.name, verse.tag + verse.number, verse.tag))
        return ordered or list(self.verses)

    def search_text(self) -> str:
        """
        All the searchable text of the song, normalised with :func:`normalise`
        """
        parts = list(self.titles)
        parts += [name for name, _ in self.authors]
        parts += [self.copyright, self.ccli_number, self.comments]
        parts += self.songbook_entries
        parts += self.topics
        parts += [verse.text for verse in self.verses]
        return normalise(' '.join(parts))


def _helper() -> OpenLyrics:
    """
    Returns the OpenLyrics object whose line handling is reused
    """
    global _open_lyrics
    if _open_lyrics is None:
        _open_lyrics = OpenLyrics(None)
    return _open_lyrics


def _texts(element, child_name: str) -> List[str]:
    """
    Returns the non-empty texts of the children of an element, e.g. all the <title> elements in <titles>
    """
    if element is None:
        return []
    return [text for text in (_helper()._text(child).strip() for child in getattr(element, child_name, []))
            if text]


def _lines_to_text(lines, version: str) -> str:
    """
    Convert a <lines> element to the text OpenLP uses. Whitespace in the XML only separates words: line breaks are
    given with <br/> (or with <line> elements before OpenLyrics 0.8). Indentation in the file is therefore removed.
    """
    element = etree.fromstring(etree.tostring(lines, with_tail=False))
    for node in element.iter():
        if node.text:
            node.text = _WHITESPACE.sub(' ', node.text)
        if node.tail and node is not element:
            node.tail = _WHITESPACE.sub(' ', node.tail)
    # The Songs plugin loses the text after a page break, so the page breaks are converted here
    for page_break in list(element.iter('{{{namespace}}}p'.format(namespace=NAMESPACE))):
        if 'page-break-after' not in str(page_break.attrib):
            continue
        marker = '[--}{--]' + (page_break.tail or '')
        previous = page_break.getprevious()
        if previous is not None:
            previous.tail = (previous.tail or '') + marker
        else:
            page_break.getparent().text = (page_break.getparent().text or '') + marker
        page_break.getparent().remove(page_break)
    comment_tag = '{{{namespace}}}comment'.format(namespace=NAMESPACE)
    if version > '0.7':
        text = _helper()._process_lines_mixed_content(element)
    else:
        text = '\n'.join(_helper()._process_lines_mixed_content(line, newlines=False)
                         for line in element if line.tag != comment_tag)
    return '\n'.join(line.strip() for line in text.split('\n'))


def _parse_authors(properties) -> List[Tuple[str, str]]:
    """
    Read the authors. Somebody who wrote both the words and the music gets the "words+music" type.
    """
    authors = []
    for author in getattr(getattr(properties, 'authors', None), 'author', []):
        name = _helper()._text(author).strip()
        author_type = author.get('type', '')
        if author_type not in ('words', 'music', 'translation'):
            author_type = ''
        if not name:
            continue
        other_type = {'words': 'music', 'music': 'words'}.get(author_type)
        if other_type and (name, other_type) in authors:
            authors[authors.index((name, other_type))] = (name, 'words+music')
        elif (name, author_type) not in authors:
            authors.append((name, author_type))
    return authors


def _parse_verses(song_xml, verse_order: List[str]) -> List[SongVerse]:
    """
    Read the verses. Verses with the same name and language are merged, like the Songs plugin does.
    Unknown verse tags become "other", and the verse order is updated to match.
    """
    lyrics = getattr(song_xml, 'lyrics', None)
    if lyrics is None or not hasattr(lyrics, 'verse'):
        raise SongFileError('The song has no verses')
    version = song_xml.get('version') or '0.8'
    verses = {}
    for verse_element in lyrics.verse:
        text = ''
        for lines in getattr(verse_element, 'lines', []):
            if text:
                text += '\n'
            text += _lines_to_text(lines, version)
            # An optional split
            if lines.get('break') is not None:
                text += '\n[---]'
        verse_def = verse_element.get('name', 'v1').lower()
        match = OpenLyrics.VERSE_TAG_SPLITTER.search(verse_def)
        tag, number, part = match.groups() if match else ('o', '', '')
        if tag not in VerseType.tags:
            tag = VerseType.tags[VerseType.Other]
        number = number or '1'
        lang = verse_element.get('lang')
        key = (tag, number, part, lang)
        if key in verses:
            verses[key].text += '\n' + text
        else:
            verses[key] = SongVerse(tag, number, part, lang, text)
        if verse_def != tag + number + part:
            verse_order[:] = [tag + number + part if entry == verse_def else entry for entry in verse_order]
    return list(verses.values())


def parse_song_xml(xml: bytes) -> FileSong:
    """
    Parse the contents of an OpenLyrics file

    :param xml: The contents of the file
    :return: The song
    :raises SongFileError: If the file is not an OpenLyrics song
    """
    try:
        song_xml = objectify.fromstring(xml, _parser)
    except etree.XMLSyntaxError as error:
        raise SongFileError(str(error)) from error
    properties = getattr(song_xml, 'properties', None)
    if properties is None:
        raise SongFileError('The song has no <properties>')
    titles = _texts(getattr(properties, 'titles', None), 'title')
    if not titles:
        raise SongFileError('The song has no title')
    # Formatting tags are new in OpenLyrics 0.8. Like OpenLP does for songs in a service file, unknown tags are added
    # temporarily, so that the song shows correctly without changing the settings.
    _helper()._process_formatting_tags(song_xml, True)
    verse_order = _helper()._text(properties.verseOrder).lower().split() if hasattr(properties, 'verseOrder') \
        else []
    song = FileSong(titles=titles)
    song.verses = _parse_verses(song_xml, verse_order)
    song.verse_order = verse_order
    song.authors = _parse_authors(properties)
    if hasattr(properties, 'copyright'):
        song.copyright = _helper()._text(properties.copyright).strip()
    if hasattr(properties, 'ccliNo'):
        song.ccli_number = _helper()._text(properties.ccliNo).strip()
    song.comments = '\n'.join(_texts(getattr(properties, 'comments', None), 'comment'))
    for songbook in getattr(getattr(properties, 'songbooks', None), 'songbook', []):
        if songbook.get('name'):
            song.songbooks.append((songbook.get('name'), songbook.get('entry', '')))
    song.topics = _texts(getattr(properties, 'themes', None), 'theme')
    return song


def parse_song_file(file_path: Path) -> FileSong:
    """
    Read an OpenLyrics file

    :param file_path: The file to read
    :return: The song
    :raises SongFileError: If the file cannot be read or is not an OpenLyrics song
    """
    try:
        xml = file_path.read_bytes()
    except OSError as error:
        raise SongFileError(str(error)) from error
    return parse_song_xml(xml)
