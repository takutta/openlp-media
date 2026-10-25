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
A one-off tool which turns the database libraries of an old portable OpenLP into folders for the folder plugins.

The source is a portable OpenLP folder: ``<source>/Data`` holds the databases, and the files the databases refer to
are somewhere else in ``<source>`` (their old absolute paths need not exist any more). Files are matched by their
sha256 hash, which the databases keep, and by name when the hash does not match. Nothing in the source is changed.

1. ``plan <source> <target>`` writes ``plan.csv``, ``missing.csv`` and ``summary.txt`` to the target.
2. ``copy <source> <target>`` carries out the (possibly edited) ``plan.csv`` and makes ``<target>/Data``.

With ``--fi`` the folders, files and the plan are in Finnish. Use it for both steps.

    .venv/Scripts/python tools/migrate_database.py [--fi] plan|copy <source> <target>
"""
import argparse
import csv
import hashlib
import json
import re
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from collections import Counter, defaultdict
from pathlib import Path, PureWindowsPath

# OpenLP from the upstream submodule, and the plugins as openlp.plugins.*, as in conftest.py
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'upstream'))
import openlp.plugins  # noqa: E402

openlp.plugins.__path__.append(str(REPO / 'plugins'))

WORDS = {
    'en': {
        'images': 'Images', 'media': 'Media', 'presentations': 'Presentations', 'songs': 'Songs',
        'services': 'Services', 'unsorted': 'Unsorted',
        'plan.csv': 'plan.csv', 'missing.csv': 'missing.csv', 'summary.txt': 'summary.txt',
        'hash cache': 'hash-cache.json',
        'copy': 'copy', 'extract': 'extract', 'song': 'song', 'duplicate': 'duplicate', 'other type': 'other-type',
        'excluded': 'excluded', 'not a song': 'not-a-song',
        'plan fields': ['action', 'type', 'source', 'target', 'size', 'sha256', 'note'],
        'missing fields': ['plugin', 'folder', 'name', 'old path', 'sha256'],
        'web page folder': 'web page folder', 'program folder': 'program folder',
        'by name': 'recognised by name', 'changed': ', contents changed',
        'also in database': 'also in the database: ', 'in database': 'in the database', 'same as': 'same as ',
        'not openlyrics': 'not an OpenLyrics file', 'same song': 'same song: ',
        'files': 'files', 'missing rows': 'missing: {count} database rows, see missing.csv',
    },
    'fi': {
        'images': 'Kuvat', 'media': 'Media', 'presentations': 'Presentaatiot', 'songs': 'Laulut',
        'services': 'Listat', 'unsorted': 'Lajittelemattomat',
        'plan.csv': 'suunnitelma.csv', 'missing.csv': 'puuttuvat.csv', 'summary.txt': 'yhteenveto.txt',
        'hash cache': 'hash-valimuisti.json',
        'copy': 'kopioi', 'extract': 'pura', 'song': 'laulu', 'duplicate': 'duplikaatti', 'other type': 'muu-tyyppi',
        'excluded': 'rajattu', 'not a song': 'ei-laulu',
        'plan fields': ['toiminto', 'tyyppi', 'lahde', 'kohde', 'koko', 'sha256', 'huom'],
        'missing fields': ['plugin', 'kansio', 'nimi', 'vanha polku', 'sha256'],
        'web page folder': 'verkkosivun kansio', 'program folder': 'ohjelmakansio',
        'by name': 'tunnistettu nimestä', 'changed': ', sisältö muuttunut',
        'also in database': 'tietokannassa myös: ', 'in database': 'tietokannassa', 'same as': 'sama kuin ',
        'not openlyrics': 'ei OpenLyrics-tiedosto', 'same song': 'sama laulu: ',
        'files': 'tiedostoa', 'missing rows': 'puuttuu: {count} tietokannan riviä, ks. puuttuvat.csv',
    },
}
# The words of the chosen language, set by main()
W = WORDS['en']
# The old libraries, and the kind of their files
LIBRARIES = {'images': 'images', 'media': 'media', 'presentations': 'presentations'}
NEW_PLUGINS = {'image_folder': 'images', 'media_folder': 'media', 'presentation_folder': 'presentations',
               'song_folder': 'songs'}
SUFFIXES = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tif', '.tiff', '.heic'},
    'media': {'.mp3', '.wav', '.wma', '.aac', '.m4a', '.ogg', '.flac', '.mp4', '.mov', '.avi', '.mkv', '.wmv',
              '.m4v', '.mpg', '.mpeg', '.webm', '.3gp', '.flv', '.vob', '.mts'},
    'presentations': {'.ppt', '.pptx', '.pps', '.ppsx', '.pptm', '.odp', '.pdf', '.key'},
    'songs': {'.xml'},
    'services': {'.osz'},
}
# Folders of saved web pages and of installed programs are not content, even if they have pictures or sounds
WEB_PAGE_FOLDER = re.compile(r'(_tiedostot|_files)$', re.IGNORECASE)
PROGRAM_SUFFIXES = {'.exe', '.msi'}
# Copied to the new Data folder. The old libraries are left out, their paths point to the old computer.
DATA_SKIPPED = {'images', 'media', 'presentations', 'songs', 'Temp'}
BAD_NAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def category(path: Path):
    return next((kind for kind, suffixes in SUFFIXES.items() if path.suffix.lower() in suffixes), None)


def clean_name(name: str) -> str:
    return BAD_NAME_CHARS.sub('_', name).strip(' .') or '_'


def sort_key(path: str):
    """Shortest path first: fewest folders, then fewest characters, then alphabetically"""
    return path.count('/'), len(path), path.lower()


def file_hash(path: Path, cache: dict) -> str:
    stat = path.stat()
    key = str(path)
    if key in cache and cache[key][:2] == [stat.st_size, stat.st_mtime_ns]:
        return cache[key][2]
    sha = hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda: file.read(1 << 20), b''):
            sha.update(chunk)
    cache[key] = [stat.st_size, stat.st_mtime_ns, sha.hexdigest()]
    return cache[key][2]


def inventory(source: Path):
    """
    All the files of the source outside its Data folder, as {relative path: (kind, reason for leaving it out)}
    """
    files = [p for p in source.rglob('*') if p.is_file() and p.relative_to(source).parts[0] != 'Data']
    program_folders = {p.parent for p in files if p.suffix.lower() in PROGRAM_SUFFIXES}
    result = {}
    for path in files:
        rel = path.relative_to(source).as_posix()
        if any(WEB_PAGE_FOLDER.search(f.name) for f in path.parents if f != source and source in f.parents):
            excluded = W['web page folder']
        elif path.parent in program_folders:
            # Only the folder of the program itself, its subfolders may be content (a folder of odds and ends with an
            # installer in it). A few files of an installer slip through, the plan lists them.
            excluded = W['program folder']
        else:
            excluded = ''
        result[rel] = (category(path), excluded)
    return result


def unsorted_target(kind: str, rel: str) -> str:
    """``old/Pictures/a.jpg`` -> ``Images/Unsorted/old/Pictures/a.jpg``, service files all go to ``Services``"""
    parts = rel.split('/')
    if kind == 'services':
        return W['services'] + '/' + parts[-1]
    return '/'.join([W[kind], W['unsorted']] + [clean_name(p) for p in parts])


def library_items(data: Path, library: str):
    """Yield (folder path in the library, name, old path, hash) for each item of an old library database"""
    db = sqlite3.connect('file:{path}?mode=ro'.format(path=(data / library / (library + '.sqlite')).as_posix()),
                         uri=True)
    folders = {fid: (name, parent) for fid, name, parent in db.execute('SELECT id, name, parent_id FROM folder')}

    def folder_path(fid):
        parts = []
        while fid in folders:
            name, fid = folders[fid]
            parts.insert(0, clean_name(name))
        return '/'.join(parts)
    for name, file_path, sha, fid in db.execute('SELECT name, file_path, file_hash, folder_id FROM item'):
        if file_path.startswith('{'):
            file_path = str(PureWindowsPath(*json.loads(file_path)['parts']))
        yield folder_path(fid), name, file_path, (sha or '').lower()
    db.close()


def setup_openlp(ini: Path):
    """Settings and a Qt application, which the OpenLyrics code of the songs plugin needs"""
    from openlp.core.common.registry import Registry
    from openlp.core.common.settings import Settings
    from openlp.plugins.filesystem_library.compat import QtCore
    app = QtCore.QCoreApplication.instance() or QtCore.QCoreApplication([])
    Registry.create()
    # Without the file name Settings() is the registry on Windows
    settings = Settings(str(ini), Settings.IniFormat)
    Registry().register('settings', settings)
    Registry().register('settings_thread', settings)
    return app, settings


def database_songs(data: Path):
    """(id, title, OpenLyrics xml) of each song in the songs database"""
    from openlp.core.db.upgrades import upgrade_db
    from openlp.plugins.songs.lib import upgrade
    from openlp.plugins.songs.lib.db import Song, init_schema
    from openlp.plugins.songs.lib.openlyricsxml import OpenLyrics
    # A copy, so that SQLAlchemy cannot touch the original. It stays in the temp folder, SQLAlchemy keeps it open on
    # Windows.
    db_path = Path(tempfile.mkdtemp()) / 'songs.sqlite'
    shutil.copy2(data / 'songs' / 'songs.sqlite', db_path)
    url = 'sqlite:///' + db_path.as_posix()
    session = init_schema(url)
    upgrade_db(url, upgrade)
    open_lyrics = OpenLyrics(None)
    songs = [(song.id, song.title, open_lyrics.song_to_xml(song).encode('utf-8'))
             for song in session.query(Song).order_by(Song.id)]
    session.close()
    return songs


def song_key(xml: bytes):
    """Songs with the same title and words are the same song. None if the file is not a song."""
    from openlp.plugins.song_folder.lib.songfile import SongFileError, normalise, parse_song_xml
    try:
        song = parse_song_xml(xml)
    except SongFileError:
        return None
    return normalise(song.title), normalise(' '.join(verse.text for verse in song.verses))


def plan(source: Path, target: Path):
    target.mkdir(parents=True, exist_ok=True)
    cache_path = target / W['hash cache']
    cache = json.loads(cache_path.read_text('utf-8')) if cache_path.exists() else {}
    files = inventory(source)
    hashes, sizes = {}, {}
    for number, (rel, (kind, _)) in enumerate(sorted(files.items()), 1):
        sizes[rel] = (source / rel).stat().st_size
        if kind:
            hashes[rel] = file_hash(source / rel, cache)
        if number % 200 == 0:
            print('{number}/{total} {files}'.format(number=number, total=len(files), files=W['files']), flush=True)
            cache_path.write_text(json.dumps(cache), 'utf-8')
    cache_path.write_text(json.dumps(cache), 'utf-8')
    by_hash, by_name = defaultdict(list), defaultdict(list)
    for rel, sha in hashes.items():
        by_hash[sha].append(rel)
        by_name[rel.rsplit('/', 1)[-1].lower()].append(rel)
    # Service files keep their files under the hash of the file
    in_services = {}
    for rel in sorted((r for r, (k, _) in files.items() if k == 'services'), key=sort_key):
        try:
            for info in zipfile.ZipFile(source / rel).infolist():
                stem = info.filename.rsplit('.', 1)[0]
                if '/' not in info.filename and len(stem) == 64:
                    in_services.setdefault(stem.lower(), (rel, info.filename, info.file_size))
        except zipfile.BadZipFile:
            pass

    rows, missing = [], []
    # 1. The items of the databases
    wanted = defaultdict(list)
    for library, kind in LIBRARIES.items():
        for folder, name, old_path, sha in library_items(source / 'Data', library):
            old = PureWindowsPath(old_path)
            target_folder = '/'.join(p for p in [W[kind], folder] if p)
            note = ''
            if sha in by_hash:
                rel = min(by_hash[sha], key=sort_key)
                entry = (W['copy'], rel, sizes[rel], sha)
            elif sha in in_services:
                osz, member, size = in_services[sha]
                entry = (W['extract'], '{osz}::{member}'.format(osz=osz, member=member), size, sha)
            else:
                # The hash is missing or the file has changed since: the file with the same name whose folders match
                # the old path best
                candidates = by_name.get(old.name.lower(), [])
                old_parts = [p.lower() for p in old.parts]

                def matching(rel):
                    parts = [p.lower() for p in rel.split('/')]
                    count = 0
                    while count < min(len(parts), len(old_parts)) and parts[-1 - count] == old_parts[-1 - count]:
                        count += 1
                    return count
                best = max((matching(c) for c in candidates), default=0)
                best_candidates = [c for c in candidates if matching(c) == best]
                if len(best_candidates) == 1 or (best_candidates and best > 1):
                    rel = min(best_candidates, key=sort_key)
                    entry = (W['copy'], rel, sizes[rel], hashes[rel])
                    note = W['by name'] + (W['changed'] if sha not in ('', 'none') else '')
                else:
                    missing.append(dict(zip(W['missing fields'], [library, folder, name, old_path, sha])))
                    continue
            file_name = clean_name(old.name if old.suffix else name)
            wanted[entry[3]].append((target_folder + '/' + file_name, entry, note))
    used_sources = set()
    for sha, places in wanted.items():
        places.sort(key=lambda place: sort_key(place[0]))
        (target_rel, (action, src, size, _), note), duplicates = places[0], places[1:]
        rows.append([action, target_rel.split('/')[0], src, target_rel, size, sha, note])
        used_sources.add(src)
        for dup_target, _, _ in duplicates:
            rows.append([W['duplicate'], dup_target.split('/')[0], src, '', size, sha,
                         W['also in database'] + dup_target])

    # 2. The songs of the database
    app, settings = setup_openlp(Path(tempfile.mkdtemp()) / 'OpenLP.ini')
    songs = {}
    for song_id, title, xml in database_songs(source / 'Data'):
        songs.setdefault(song_key(xml), title)
        rows.append([W['song'], W['songs'], 'songs.sqlite#{id}'.format(id=song_id),
                     '{folder}/{name}.xml'.format(folder=W['songs'], name=clean_name(title)), len(xml), '', title])

    # 3. The files which are not in a database
    referenced = set(wanted)
    first_of_hash = {}
    for rel in sorted(files, key=sort_key):
        kind, excluded = files[rel]
        if rel in used_sources:
            continue
        sha = hashes.get(rel, '')
        if not kind:
            rows.append([W['other type'], '', rel, '', sizes[rel], '', ''])
            continue
        kind_name = W[kind]
        if excluded:
            rows.append([W['excluded'], kind_name, rel, '', sizes[rel], sha, excluded])
        elif sha in referenced:
            rows.append([W['duplicate'], kind_name, rel, '', sizes[rel], sha, W['in database']])
        elif sha in first_of_hash:
            rows.append([W['duplicate'], kind_name, rel, '', sizes[rel], sha, W['same as'] + first_of_hash[sha]])
        elif kind == 'songs' and (key := song_key((source / rel).read_bytes())) is None:
            rows.append([W['not a song'], kind_name, rel, '', sizes[rel], sha, W['not openlyrics']])
        elif kind == 'songs' and key in songs:
            rows.append([W['duplicate'], kind_name, rel, '', sizes[rel], sha, W['same song'] + songs[key]])
        else:
            if kind == 'songs':
                songs[key] = rel
            first_of_hash[sha] = rel
            rows.append([W['copy'], kind_name, rel, unsorted_target(kind, rel), sizes[rel], sha, ''])

    # Different files with the same name get a number, like " (2)". Windows does not care about the case.
    taken = set()
    for row in rows:
        if not row[3]:
            continue
        stem, dot, suffix = row[3].rpartition('.')
        number = 1
        while row[3].lower() in taken:
            number += 1
            row[3] = '{stem} ({number}).{suffix}'.format(stem=stem, number=number, suffix=suffix)
        taken.add(row[3].lower())

    with (target / W['plan.csv']).open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.writer(file, delimiter=';')
        writer.writerow(W['plan fields'])
        writer.writerows(rows)
    with (target / W['missing.csv']).open('w', encoding='utf-8-sig', newline='') as file:
        writer = csv.DictWriter(file, W['missing fields'], delimiter=';')
        writer.writeheader()
        writer.writerows(missing)
    count, size = Counter(), Counter()
    for row in rows:
        count[row[0], row[1]] += 1
        size[row[0], row[1]] += int(row[4])
    lines = ['{action:12} {kind:14} {count:6} {files} {size:8.2f} GB'.format(
        action=action, kind=kind, count=count[action, kind], files=W['files'], size=size[action, kind] / 1e9)
        for action, kind in sorted(count)]
    lines.append(W['missing rows'].format(count=len(missing)))
    (target / W['summary.txt']).write_text('\n'.join(lines) + '\n', 'utf-8')
    print('\n'.join(lines))


def copy(source: Path, target: Path):
    plan_path = target / W['plan.csv']
    if not plan_path.exists():
        sys.exit('{path} was not found. Run plan first, with --fi if you used it.'.format(path=plan_path))
    action, _, src, dst, size = W['plan fields'][:5]
    with plan_path.open(encoding='utf-8-sig', newline='') as file:
        rows = [row for row in csv.DictReader(file, delimiter=';')
                if row[action] in (W['copy'], W['extract'], W['song'])]
    app, settings = setup_openlp(Path(tempfile.mkdtemp()) / 'OpenLP.ini')
    songs = {'songs.sqlite#{id}'.format(id=song_id): xml for song_id, _, xml in database_songs(source / 'Data')}
    for number, row in enumerate(rows, 1):
        destination = target / row[dst]
        if destination.exists() and destination.stat().st_size == int(row[size]):
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if row[action] == W['song']:
            destination.write_bytes(songs[row[src]])
        elif row[action] == W['extract']:
            osz, member = row[src].split('::')
            with zipfile.ZipFile(source / osz) as archive, archive.open(member) as file, destination.open('wb') as out:
                shutil.copyfileobj(file, out, 1 << 20)
        else:
            shutil.copy2(source / row[src], destination)
        if number % 100 == 0:
            print('{number}/{total}'.format(number=number, total=len(rows)), flush=True)
    for kind in NEW_PLUGINS.values():
        (target / W[kind]).mkdir(exist_ok=True)
    make_data(source / 'Data', target / 'Data')


def make_data(old_data: Path, new_data: Path):
    """Copy the rest of the old data folder and turn the folder plugins on in its settings"""
    from openlp.core.common.enum import PluginStatus
    from openlp.core.common.settings import Settings
    shutil.copytree(old_data, new_data, dirs_exist_ok=True,
                    ignore=lambda folder, names: DATA_SKIPPED if Path(folder) == old_data else [])
    settings = Settings(str(new_data / 'OpenLP.ini'), Settings.IniFormat)
    for plugin, kind in NEW_PLUGINS.items():
        # Relative to the portable folder, see FileSystemLibraryItem.root_path
        settings.setValue(plugin + '/root folder', Path(W[kind]))
        settings.setValue(plugin + '/status', int(PluginStatus.Active))
    for plugin in ['images', 'media', 'presentations', 'songs']:
        settings.setValue(plugin + '/status', int(PluginStatus.Inactive))
    settings.remove('core/recent files')
    settings.sync()


def main():
    global W
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('step', choices=['plan', 'copy'])
    parser.add_argument('source', type=Path, help='the old portable OpenLP folder, with Data in it')
    parser.add_argument('target', type=Path, help='the new folder')
    parser.add_argument('--fi', action='store_true', help='Finnish names for the folders, files and the plan')
    args = parser.parse_args()
    W = WORDS['fi' if args.fi else 'en']
    {'plan': plan, 'copy': copy}[args.step](args.source.resolve(), args.target.resolve())


if __name__ == '__main__':
    main()
