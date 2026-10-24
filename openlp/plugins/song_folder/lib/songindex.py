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
A search index of the songs in the library. The index is only a cache in memory: the files are always the truth, and
the index can be thrown away and built again at any time. A file is read again only when its modification time or size
has changed. The index can be saved to a cache file, so that a big library starts quickly.
"""
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from openlp.plugins.song_folder.lib.songfile import FileSong, SongFileError, SongVerse, normalise, parse_song_file


log = logging.getLogger(__name__)

# Change this when FileSong or the search text changes, so that old caches are thrown away
CACHE_VERSION = 1


@dataclass
class _Entry:
    stamp: tuple
    song: Optional[FileSong]
    error: str
    search_text: str


class SongIndex(object):
    """
    Keeps the parsed songs of the library in memory
    """
    def __init__(self):
        self._entries: Dict[Path, _Entry] = {}
        # Set when the entries change, so that the cache is only written when needed
        self.changed = False

    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, file_path: Path) -> bool:
        return file_path in self._entries

    def _entry(self, file_path: Path) -> Optional[_Entry]:
        """
        Returns the up to date entry of a file, reading the file if it is new or has changed

        :param file_path: The song file
        """
        try:
            stat = file_path.stat()
        except OSError:
            self._entries.pop(file_path, None)
            return None
        stamp = (stat.st_mtime_ns, stat.st_size)
        entry = self._entries.get(file_path)
        if entry is None or entry.stamp != stamp:
            try:
                song = parse_song_file(file_path)
                entry = _Entry(stamp, song, '', normalise(file_path.stem) + ' ' + song.search_text())
            except SongFileError as error:
                log.warning('Could not read the song {path}: {error}'.format(path=file_path, error=error))
                entry = _Entry(stamp, None, str(error), normalise(file_path.stem))
            self._entries[file_path] = entry
            self.changed = True
        return entry

    def get(self, file_path: Path) -> Optional[FileSong]:
        """
        Returns the song in a file, or None if it cannot be read

        :param file_path: The song file
        """
        entry = self._entry(file_path)
        return entry.song if entry else None

    def error(self, file_path: Path) -> str:
        """
        Returns the reason why a file could not be read, or an empty string

        :param file_path: The song file
        """
        entry = self._entry(file_path)
        return entry.error if entry else ''

    def update(self, file_paths: Iterable[Path]):
        """
        Make the index match a list of files: changed files are read again and missing ones are forgotten

        :param file_paths: All the song files of the library
        """
        file_paths = set(file_paths)
        for file_path in list(self._entries):
            if file_path not in file_paths:
                del self._entries[file_path]
                self.changed = True
        for file_path in file_paths:
            self._entry(file_path)

    def forget(self, file_path: Path):
        """
        Remove a file, or all the files in a folder, from the index

        :param file_path: The file or folder
        """
        for path in list(self._entries):
            if path == file_path or path.is_relative_to(file_path):
                del self._entries[path]
                self.changed = True

    def clear(self):
        self._entries.clear()
        self.changed = True

    def load(self, cache_path: Path):
        """
        Read the index from a cache file. Files that changed since are read again by :meth:`update`.
        A missing or broken cache is ignored.

        :param cache_path: The cache file
        """
        try:
            data = json.loads(cache_path.read_text(encoding='utf-8'))
            if data.get('version') != CACHE_VERSION:
                return
            entries = {}
            for path, entry in data['entries'].items():
                song = entry['song']
                if song is not None:
                    song = FileSong(**dict(song, authors=[tuple(author) for author in song['authors']],
                                           songbooks=[tuple(book) for book in song['songbooks']],
                                           verses=[SongVerse(**verse) for verse in song['verses']]))
                entries[Path(path)] = _Entry(tuple(entry['stamp']), song, entry['error'], entry['search_text'])
        except (OSError, ValueError, KeyError, TypeError) as error:
            log.info('Song index cache {path} not used: {error}'.format(path=cache_path, error=error))
            return
        self._entries = entries
        self.changed = False

    def save(self, cache_path: Path):
        """
        Write the index to a cache file, if it has changed

        :param cache_path: The cache file
        """
        if not self.changed:
            return
        data = {'version': CACHE_VERSION,
                'entries': {str(path): {'stamp': list(entry.stamp),
                                        'song': asdict(entry.song) if entry.song else None,
                                        'error': entry.error, 'search_text': entry.search_text}
                            for path, entry in self._entries.items()}}
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(dir=cache_path.parent, prefix='.', suffix='.tmp')
            try:
                with os.fdopen(handle, 'w', encoding='utf-8') as temp_file:
                    json.dump(data, temp_file, ensure_ascii=False)
                os.replace(temp_name, cache_path)
            except BaseException:
                Path(temp_name).unlink(missing_ok=True)
                raise
        except OSError as error:
            log.warning('Could not save the song index cache {path}: {error}'.format(path=cache_path, error=error))
            return
        self.changed = False

    def search(self, text: str) -> List[Path]:
        """
        Find the songs which contain all the words of the text, in any field. The file name is searched too.

        :param text: The text to search for
        :return: The matching files
        """
        words = normalise(text).split()
        return [path for path, entry in self._entries.items()
                if all(word in entry.search_text for word in words)]
