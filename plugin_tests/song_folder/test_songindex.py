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
Test the search index of the song folder plugin
"""
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from openlp.plugins.song_folder.lib.songindex import SongIndex


def make_song(title: str, lyrics: str, author: str = 'Someone') -> str:
    return '''<song xmlns="http://openlyrics.info/namespace/2009/song" version="0.8">
      <properties><titles><title>{title}</title></titles><authors><author>{author}</author></authors></properties>
      <lyrics><verse name="v1"><lines>{lyrics}</lines></verse></lyrics></song>'''.format(title=title, lyrics=lyrics,
                                                                                         author=author)


@pytest.fixture
def song_root(temp_folder):
    root = Path(temp_folder) / 'songs'
    root.mkdir()
    (root / 'grace.xml').write_text(make_song('Amazing Grace', 'How sweet the sound', 'John Newton'))
    (root / 'friend.xml').write_text(make_song('What a Friend', 'All our sins and griefs to bear'))
    (root / 'broken.xml').write_text('<html/>')
    return root


def test_get_and_error(settings, song_root):
    """Songs are read on demand, and broken files have an error"""
    index = SongIndex()

    assert index.get(song_root / 'grace.xml').title == 'Amazing Grace'
    assert index.error(song_root / 'grace.xml') == ''
    assert index.get(song_root / 'broken.xml') is None
    assert index.error(song_root / 'broken.xml')
    assert index.get(song_root / 'missing.xml') is None
    assert len(index) == 2


def test_search(settings, song_root):
    """All the words must be found, in any field, in any order and case"""
    index = SongIndex()
    index.update(song_root.glob('*.xml'))

    assert index.search('newton GRACE') == [song_root / 'grace.xml']
    assert index.search('griefs, sins!') == [song_root / 'friend.xml']
    assert index.search('grace friend') == []
    # The file name is searched too, also for files that cannot be read
    assert index.search('broken') == [song_root / 'broken.xml']
    assert len(index.search('')) == 3


def test_changed_file_is_read_again(settings, song_root):
    """A file is read again only when it has changed"""
    index = SongIndex()
    path = song_root / 'grace.xml'
    first = index.get(path)

    with patch('openlp.plugins.song_folder.lib.songindex.parse_song_file') as mocked_parse:
        assert index.get(path) is first
        mocked_parse.assert_not_called()

    path.write_text(make_song('Amazing Grace (new)', 'Changed'))
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    assert index.get(path).title == 'Amazing Grace (new)'


def test_update_forgets_removed_files(settings, song_root):
    """update() makes the index match the files of the library"""
    index = SongIndex()
    index.update(song_root.glob('*.xml'))

    index.update([song_root / 'grace.xml'])

    assert song_root / 'grace.xml' in index
    assert song_root / 'friend.xml' not in index


def test_forget_folder(settings, song_root):
    """Forgetting a folder forgets the files in it"""
    index = SongIndex()
    (song_root / 'sub').mkdir()
    (song_root / 'sub' / 'other.xml').write_text(make_song('Other', 'Text'))
    index.update(list(song_root.glob('*.xml')) + [song_root / 'sub' / 'other.xml'])

    index.forget(song_root / 'sub')

    assert song_root / 'sub' / 'other.xml' not in index
    assert song_root / 'grace.xml' in index
