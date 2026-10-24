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
has changed.
"""
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from openlp.plugins.song_folder.lib.songfile import FileSong, SongFileError, normalise, parse_song_file


log = logging.getLogger(__name__)


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

    def clear(self):
        self._entries.clear()

    def search(self, text: str) -> List[Path]:
        """
        Find the songs which contain all the words of the text, in any field. The file name is searched too.

        :param text: The text to search for
        :return: The matching files
        """
        words = normalise(text).split()
        return [path for path, entry in self._entries.items()
                if all(word in entry.search_text for word in words)]
