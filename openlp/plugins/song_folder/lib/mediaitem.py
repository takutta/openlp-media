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
import glob
import logging
import shutil
from collections import namedtuple
from pathlib import Path
from typing import Any, List, Optional

import mako.exceptions
import mako.template
from PySide6 import QtCore, QtWidgets

from openlp.core.common import sha256_file_hash
from openlp.core.common.applocation import AppLocation
from openlp.core.common.enum import SongFirstSlideMode
from openlp.core.common.i18n import UiStrings, translate
from openlp.core.lib import ServiceItemContext, check_item_selected, create_separated_list
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import critical_error_message_box
from openlp.core.state import State
from openlp.core.ui.icons import UiIcons
from openlp.core.ui.media import get_supported_media_suffix
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole, \
    move_to_trash
from openlp.plugins.song_folder.forms.editsongform import SongFileEditForm
from openlp.plugins.song_folder.lib.songfile import FORCED_SPLIT, FileSong, SongFileError, parse_song_file, \
    parse_song_xml
from openlp.plugins.song_folder.lib.songindex import SongIndex
from openlp.plugins.song_folder.lib.songwriter import song_file_name, write_song_file
from openlp.plugins.songs.lib import VerseType
from openlp.plugins.songs.lib.db import AuthorType
from openlp.plugins.songs.lib.ui import SongStrings


log = logging.getLogger(__name__)

# The settings of the Songs plugin which show the first line of the next slide, by verse tag
PREVIEW_SETTINGS = {'i': 'songs/preview_intro', 'v': 'songs/preview_verse', 'c': 'songs/preview_chorus',
                    'b': 'songs/preview_bridge', 'p': 'songs/preview_pre_chorus', 'e': 'songs/preview_ending',
                    'o': 'songs/preview_other'}

Authors = namedtuple('Authors', ['words', 'music', 'words_music', 'translation', 'none', 'all'])


def get_authors(song: FileSong) -> Authors:
    """
    Group the authors of a song by their type, like the Songs plugin does for its footer
    """
    groups = {AuthorType.Words: [], AuthorType.Music: [], AuthorType.WordsAndMusic: [], AuthorType.Translation: [],
              AuthorType.NoType: []}
    for name, author_type in song.authors:
        groups.get(author_type, groups[AuthorType.NoType]).append(name)
    words_music = groups[AuthorType.WordsAndMusic]
    all_authors = (words_music + groups[AuthorType.Words] + groups[AuthorType.Music] + groups[AuthorType.Translation] +
                   groups[AuthorType.NoType])
    return Authors(groups[AuthorType.Words], groups[AuthorType.Music], words_music, groups[AuthorType.Translation],
                   groups[AuthorType.NoType], all_authors)


class SongFolderMediaItem(FileSystemLibraryItem):
    """
    The media manager item for the Song Folder plugin. Lists the OpenLyrics files of a folder on disk.
    """
    song_folder_go_live = QtCore.Signal(list)
    song_folder_add_to_service = QtCore.Signal(list)
    log.info('{name} SongFolderMediaItem loaded'.format(name=__name__))

    def __init__(self, parent, plugin):
        self.index = SongIndex()
        self._edit_song_form = None
        super().__init__(parent, plugin)

    @property
    def edit_song_form(self) -> SongFileEditForm:
        """
        The song editor, created when it is first needed
        """
        if self._edit_song_form is None:
            self._edit_song_form = SongFileEditForm(self.main_window)
        return self._edit_song_form

    def required_icons(self):
        """
        Songs can be created and edited
        """
        super().required_icons()
        self.has_new_icon = True
        self.has_edit_icon = True

    def retranslate_ui(self):
        """
        Translate the user interface
        """
        super().retranslate_ui()
        self.on_new_prompt = translate('SongFolderPlugin.MediaItem', 'Select Songs')
        self.on_new_file_masks = translate('SongFolderPlugin.MediaItem',
                                           'OpenLyrics Files (*.xml);;{files} (*)').format(files=UiStrings().AllFiles)
        self.search_text_label.setText('{text}:'.format(text=UiStrings().Search))
        self.search_text_button.setText(UiStrings().Search)
        self.search_text_edit.setPlaceholderText(translate('SongFolderPlugin.MediaItem',
                                                           'Search titles, lyrics, authors...'))

    def setup_item(self):
        """
        Do some additional setup
        """
        self.song_folder_go_live.connect(self.go_live_remote)
        self.song_folder_add_to_service.connect(self.add_to_service_remote)
        self.single_service_item = False
        self.has_search = True
        # Allow DnD from the desktop
        self.list_view.activateDnD()

    def add_end_header_bar(self):
        """
        Add the search box between the toolbar and the list
        """
        self.add_search_to_toolbar()

    def is_supported_file(self, file_path: Path) -> bool:
        """
        List the OpenLyrics files

        :param file_path: The file to check
        """
        return file_path.suffix.lower() == '.xml'

    def load_item(self, file_path: Path) -> QtWidgets.QTreeWidgetItem:
        """
        Show the title of the song. Files which cannot be read are shown with their file name and an error icon.

        :param file_path: The song file
        """
        song = self.index.get(file_path)
        if song:
            tree_item = QtWidgets.QTreeWidgetItem([song.title])
            tree_item.setIcon(0, UiIcons().music)
            tooltip = [song.title]
            if song.alternate_title:
                tooltip.append(song.alternate_title)
            if song.authors:
                tooltip.append(create_separated_list([name for name, _ in song.authors]))
            tooltip.append(str(file_path))
            tree_item.setToolTip(0, '\n'.join(tooltip))
        else:
            tree_item = QtWidgets.QTreeWidgetItem([file_path.name])
            tree_item.setIcon(0, UiIcons().error)
            tree_item.setToolTip(0, '{path}\n{error}'.format(path=file_path, error=self.index.error(file_path)))
        return tree_item

    def delete_item(self, file_path: Path):
        """
        Forget a song which was moved to the trash

        :param file_path: The song file
        """
        self.index.forget(file_path)

    def reload(self, select_paths: Optional[List[Path]] = None):
        """
        Reload the library from disk, update the search index and filter the list again
        """
        super().reload(select_paths)
        self.index.update(self.get_file_list())
        self.index.save(self.index_cache_path)
        self.filter_list(self.search_text_edit.displayText())

    @property
    def index_cache_path(self) -> Path:
        """
        The cache of the search index, in the data folder of the plugin
        """
        return AppLocation.get_section_data_path(self.settings_section) / 'index.json'

    def initialise(self):
        """
        Read the search index from its cache before the library is loaded, so that only changed files are read
        """
        self.index.load(self.index_cache_path)
        super().initialise()

    # Searching

    def on_search_text_button_clicked(self):
        """
        Filter the list with the search text
        """
        self.filter_list(self.search_text_edit.displayText())

    def on_search_text_edit_changed(self, text: str):
        """
        Filter the list while typing. The index is in memory, so this is fast.

        :param text: The search text
        """
        self.filter_list(text)

    def filter_list(self, text: str):
        """
        Show only the songs which match the search text, and the folders containing them

        :param text: The search text, an empty text shows everything
        """
        matches = set(self.index.search(text)) if text.strip() else None
        self._filter_item(self.list_view.invisibleRootItem(), matches)

    def _filter_item(self, tree_item: QtWidgets.QTreeWidgetItem, matches: Optional[set]) -> bool:
        """
        Hide the children of a tree item which do not match, and return True if anything is left visible
        """
        visible = False
        for index in range(tree_item.childCount()):
            child = tree_item.child(index)
            item_type = child.data(0, ItemTypeRole)
            if item_type == ItemType.Folder:
                child_visible = self._filter_item(child, matches)
                if matches is not None:
                    child.setExpanded(child_visible)
                child_visible = child_visible or matches is None
            elif item_type == ItemType.File:
                child_visible = matches is None or child.data(0, QtCore.Qt.ItemDataRole.UserRole) in matches
            else:
                # The placeholder shown when no folder has been chosen
                child_visible = True
            child.setHidden(not child_visible)
            visible = visible or child_visible
        return visible

    @QtCore.Slot(str, bool, result=list)
    def search(self, string: str, show_error: bool = True) -> list[list[Any]]:
        """
        Search the songs for the remote API

        :param string: The text to search for
        :param show_error: Unused
        :return: A list of [file path, title, alternate title]
        """
        results = []
        for file_path in sorted(self.index.search(string)):
            song = self.index.get(file_path)
            if song:
                results.append([str(file_path), song.title, song.alternate_title])
        return results

    # Building the service item

    def generate_slide_data(self, service_item, *, item=None, remote=False, context=ServiceItemContext.Service,
                            **kwargs):
        """
        Generate the slides of a song

        :param service_item: The service item to be built on
        :param item: The tree item to be used
        :param remote: Triggered from remote
        :param context: Why is it being generated
        :param kwargs: Consume other unused args specified by the base implementation, but not use by this one.
        """
        tree_item = self._get_tree_item(item)
        if tree_item is None or tree_item.data(0, ItemTypeRole) != ItemType.File:
            return False
        file_path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        # The file is read again instead of taken from the index, so that the slides are always up to date and the
        # formatting tags of the song are loaded
        try:
            song = parse_song_file(file_path)
        except SongFileError as error:
            if not remote:
                critical_error_message_box(
                    translate('SongFolderPlugin.MediaItem', 'Could not read the song'),
                    translate('SongFolderPlugin.MediaItem', 'The file {name} could not be read as an OpenLyrics '
                              'song:\n{error}').format(name=file_path, error=error if file_path.exists() else
                                                       translate('SongFolderPlugin.MediaItem', 'File not found.')))
            return False
        service_item.title = song.title
        service_item.add_capability(ItemCapabilities.CanPreview)
        service_item.add_capability(ItemCapabilities.CanLoop)
        service_item.add_capability(ItemCapabilities.CanSoftBreak)
        service_item.add_capability(ItemCapabilities.CanEdit)
        service_item.add_capability(ItemCapabilities.OnLoadUpdate)
        service_item.edit_id = str(file_path)
        if song.theme:
            service_item.theme = song.theme
        authors = get_authors(song)
        footer_vars = self.generate_footer(service_item, song, authors)
        self.generate_first_slide(service_item, song, footer_vars)
        self.generate_verses(service_item, song)
        service_item.data_string = {
            'title': song.title,
            'alternate_title': song.alternate_title,
            'authors': ', '.join(authors.all),
            'ccli_number': song.ccli_number,
            'copyright': song.copyright,
            'file path': str(file_path)
        }
        self.add_background_audio(service_item, file_path)
        # The core only knows the icons of its own plugins
        service_item.icon = UiIcons().music
        return True

    def generate_verses(self, service_item, song: FileSong):
        """
        Add the verses in the verse order. Like the Songs plugin, the slides can be in upper case, and the first line
        of the next slide can be shown at the end of a slide.

        :param service_item: The service item to be amended
        :param song: The song
        """
        uppercase = bool(self.settings.value('songs/uppercase songs'))
        preview_types = set()
        if self.settings.value('songs/preview_enabled'):
            preview_types = {tag for tag, setting in PREVIEW_SETTINGS.items() if self.settings.value(setting)}
        pages = []
        for verse in song.ordered_verses():
            verse_def = '{tag}{number}'.format(tag=VerseType.translated_tag(verse.tag), number=verse.number)
            pages.extend((verse, verse_def, page) for page in FORCED_SPLIT.split(verse.text))
        for index, (verse, verse_def, page) in enumerate(pages):
            if verse.tag in preview_types and index + 1 < len(pages):
                next_verse, _, next_page = pages[index + 1]
                next_lines = next_page.strip('\n').splitlines()
                # The next verse is previewed only if its type is previewed too
                if next_lines and (next_verse is verse or next_verse.tag in preview_types):
                    page = page.rstrip() + '\n{preview}' + next_lines[0] + '{/preview}'
            if uppercase:
                page = '{uc}' + page + '{/uc}'
            service_item.add_from_text(page, verse_def)

    def generate_first_slide(self, service_item, song: FileSong, footer_vars: dict):
        """
        Add the first slide which the Songs plugin can show before the lyrics: the songbooks, or the footer

        :param service_item: The service item to be amended
        :param song: The song
        :param footer_vars: The variables of the footer template
        """
        mode = self.settings.value('songs/first slide mode')
        metadata = {'songs_first_slide_type': mode}
        if mode == SongFirstSlideMode.Songbook and song.songbooks:
            first_slide = '\n' + ''.join('{entry}\n\n'.format(entry=entry) for entry in song.songbook_entries)
            service_item.add_from_text(first_slide, 'O1', metadata=metadata)
        elif mode == SongFirstSlideMode.Footer:
            first_slide = self.render_footer(dict(footer_vars, first_slide=True))
            if first_slide is None:
                first_slide = '\n'.join(service_item.raw_footer)
            service_item.add_from_text(first_slide, 'O2', footer_html='', metadata=metadata)

    def background_audio_files(self, file_path: Path) -> List[Path]:
        """
        The audio files next to a song with the same name, e.g. "Song.mp3" for "Song.xml"

        :param file_path: The song file
        """
        audio, _ = get_supported_media_suffix()
        suffixes = {suffix[1:].lower() for suffix in audio if suffix}
        try:
            candidates = sorted(file_path.parent.glob(glob.escape(file_path.stem) + '.*'))
            return [path for path in candidates if path.suffix.lower() in suffixes and
                    path.stem.casefold() == file_path.stem.casefold() and path.is_file()]
        except OSError:
            return []

    def find_background_audio(self, file_path: Path) -> Optional[Path]:
        """
        The background audio of a song is the first audio file next to it with the same name

        :param file_path: The song file
        :return: The audio file, or None if there is none
        """
        return next(iter(self.background_audio_files(file_path)), None)

    def related_files(self, file_path: Path) -> List[Path]:
        """
        The audio files of a song are copied, moved and deleted together with it
        """
        return self.background_audio_files(file_path)

    def save_background_audio(self, file_path: Path, audio_path: Optional[Path]) -> List[str]:
        """
        Make an audio file the background audio of a song. It is copied next to the song with the same name, and the
        other audio files of the song are moved to the trash.

        :param file_path: The song file
        :param audio_path: The audio file, or None to remove the background audio
        :return: The names of the files which could not be removed or copied
        """
        current = self.background_audio_files(file_path)
        if audio_path == next(iter(current), None):
            return []
        keep = [path for path in current if audio_path and path.resolve() == audio_path.resolve()]
        failed = [path.name for path in current if path not in keep and not move_to_trash(path)]
        if audio_path and not keep:
            target_path = file_path.with_name(file_path.stem + audio_path.suffix)
            try:
                if target_path.exists():
                    raise FileExistsError(str(target_path))
                shutil.copy2(audio_path, target_path)
            except OSError as error:
                failed.append('{name} ({error})'.format(name=audio_path.name, error=error))
        return failed

    def add_background_audio(self, service_item, file_path: Path):
        """
        Play the audio file of the song in the background, like the linked audio of the Songs plugin

        :param service_item: The service item to be amended
        :param file_path: The song file
        """
        audio_path = self.find_background_audio(file_path)
        if not audio_path or not State().check_preconditions('media'):
            return
        service_item.add_capability(ItemCapabilities.HasBackgroundAudio)
        service_item.background_audio = [(audio_path, sha256_file_hash(audio_path))]
        service_item.set_media_length(self.media_controller.media_length(audio_path))
        service_item.metadata.append('<em>{label}:</em> {media}'.format(
            label=translate('SongsPlugin.MediaItem', 'Media'), media=audio_path.name))

    def generate_footer(self, service_item, song: FileSong, authors: Authors):
        """
        Build the footer with the footer template of the Songs plugin, so that both plugins show songs the same way

        :param service_item: The service item to be amended
        :param song: The song
        :param authors: The authors of the song
        :return: The variables of the footer template
        """
        service_item.audit = [song.title, authors.all, song.copyright, song.ccli_number]
        service_item.raw_footer = [song.title]
        for label, names in ((translate('OpenLP.Ui', 'Written by'), authors.none),
                             (AuthorType.get_translated_type(AuthorType.WordsAndMusic), authors.words_music),
                             (AuthorType.get_translated_type(AuthorType.Words), authors.words),
                             (AuthorType.get_translated_type(AuthorType.Music), authors.music),
                             (AuthorType.get_translated_type(AuthorType.Translation), authors.translation)):
            if names:
                service_item.raw_footer.append('{label}: {names}'.format(label=label,
                                                                         names=create_separated_list(names)))
        if song.copyright:
            service_item.raw_footer.append('{symbol} {copyright}'.format(symbol=SongStrings().CopyrightSymbol,
                                                                         copyright=song.copyright))
        if song.songbooks:
            service_item.raw_footer.append(', '.join(song.songbook_entries))
        ccli_license = self.settings.value('core/ccli number')
        if ccli_license:
            service_item.raw_footer.append(translate('SongsPlugin.MediaItem', 'CCLI License: ') + ccli_license)
        footer_vars = {
            'title': song.title,
            'alternate_title': song.alternate_title,
            'authors_none_label': translate('OpenLP.Ui', 'Written by'),
            'authors_none': authors.none,
            'authors_words_label': AuthorType.get_translated_type(AuthorType.Words),
            'authors_words': authors.words,
            'authors_music_label': AuthorType.get_translated_type(AuthorType.Music),
            'authors_music': authors.music,
            'authors_words_music_label': AuthorType.get_translated_type(AuthorType.WordsAndMusic),
            'authors_words_music': authors.words_music,
            'authors_translation_label': AuthorType.get_translated_type(AuthorType.Translation),
            'authors_translation': authors.translation,
            'authors_words_all': authors.words + authors.words_music,
            'authors_music_all': authors.music + authors.words_music,
            'copyright': song.copyright,
            'songbook_entries': song.songbook_entries,
            'ccli_license': ccli_license,
            'ccli_license_label': translate('SongsPlugin.MediaItem', 'CCLI License'),
            'ccli_number': song.ccli_number,
            'topics': song.topics,
            'first_slide': False
        }
        footer_html = self.render_footer(footer_vars)
        if footer_html is not None:
            service_item.footer_html = footer_html
        return footer_vars

    def render_footer(self, footer_vars: dict) -> Optional[str]:
        """
        Render the footer template of the Songs plugin

        :param footer_vars: The variables of the template
        :return: The HTML, or None if the template is broken and the plain footer should be used
        """
        try:
            footer_template = self.settings.value('songs/footer template')
            return mako.template.Template(footer_template).render_unicode(**footer_vars).replace('\n', '')
        except (mako.exceptions.SyntaxException, mako.exceptions.CompileException):
            log.error('Failed to render Song footer html:\n' + mako.exceptions.text_error_template().render())
            return None

    def service_load(self, item):
        """
        Set the icon of a service item that was loaded from a service file

        :param item: The service item that was loaded
        """
        item.icon = UiIcons().music
        # The edit id is not saved in service files, but the path of the song is
        file_path = item.data_string.get('file path') if isinstance(item.data_string, dict) else None
        if file_path and Path(file_path).is_file():
            item.edit_id = file_path
        elif item.is_capable(ItemCapabilities.CanEdit):
            item.remove_capability(ItemCapabilities.CanEdit)
        return item

    # Editing

    def on_new_click(self):
        """
        Write a new song into the selected folder
        """
        if self._require_root():
            self.edit_song_file(None)

    def on_edit_click(self):
        """
        Edit the selected song. The song is updated in the service too.
        """
        if not check_item_selected(self.list_view, UiStrings().SelectEdit):
            return
        tree_item = self.list_view.currentItem()
        if tree_item is None or tree_item.data(0, ItemTypeRole) != ItemType.File:
            return
        file_path = self.edit_song_file(tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole))
        if file_path:
            service_item = self.build_service_item(self.create_item_from_id(file_path), remote=True,
                                                   context=ServiceItemContext.Service)
            if service_item:
                self.service_manager.replace_service_item(service_item)

    def on_remote_edit(self, item_id: str, preview: bool = False):
        """
        Edit a song from the service or from the preview

        :param item_id: The path of the song
        :param preview: The song is edited from the preview
        :return: The updated service item, or None if nothing was changed
        """
        tree_item = self.create_item_from_id(item_id)
        if tree_item.data(0, ItemTypeRole) != ItemType.File:
            return None
        file_path = self.edit_song_file(Path(item_id))
        if not file_path:
            return None
        service_item = self.build_service_item(self.create_item_from_id(file_path), remote=True)
        if service_item and preview:
            # A song can only be edited from the preview if it comes from the plugin
            service_item.from_plugin = True
        return service_item

    def edit_song_file(self, file_path: Optional[Path]) -> Optional[Path]:
        """
        Show the song editor and save the song. Everything in the file that the editor does not know about is kept.

        :param file_path: The song to edit, or None for a new song in the current folder
        :return: The file that was saved, or None if the editor was cancelled
        """
        original = None
        song = None
        if file_path:
            try:
                original = file_path.read_bytes()
                song = parse_song_xml(original)
            except (OSError, SongFileError) as error:
                critical_error_message_box(
                    translate('SongFolderPlugin.MediaItem', 'Could not read the song'),
                    translate('SongFolderPlugin.MediaItem', 'The file {name} could not be read as an OpenLyrics '
                              'song:\n{error}').format(name=file_path, error=error))
                return None
        self.edit_song_form.audio_folder = file_path.parent if file_path else self.current_folder
        self.edit_song_form.load_song(song, self.find_background_audio(file_path) if file_path else None)
        while self.edit_song_form.exec() == QtWidgets.QDialog.DialogCode.Accepted:
            song = self.edit_song_form.song
            target_path = file_path or song_file_name(song.title, self.current_folder)
            if file_path and not self._can_overwrite(file_path, original):
                return None
            try:
                write_song_file(song, target_path, keep_contents=file_path is not None)
            except SongFileError as error:
                # The form keeps the song, so that nothing is lost
                critical_error_message_box(message=translate('SongFolderPlugin.MediaItem',
                                                             'Could not save the song: {error}').format(error=error))
                continue
            # A new song does not touch audio files which happen to have its name, unless audio was chosen
            failed = self.save_background_audio(target_path, self.edit_song_form.audio_path) \
                if file_path or self.edit_song_form.audio_path else []
            if failed:
                critical_error_message_box(message=translate('SongFolderPlugin.MediaItem',
                                                             'The background audio could not be changed:\n{names}'
                                                             ).format(names='\n'.join(failed)))
            # The file might have the same size and time stamp as before
            self.index.forget(target_path)
            self.reload(select_paths=[target_path])
            return target_path
        return None

    def _can_overwrite(self, file_path: Path, original: Optional[bytes]) -> bool:
        """
        Ask before saving over a file which was changed on disk while it was being edited
        """
        try:
            current = file_path.read_bytes()
        except OSError:
            current = None
        if current == original:
            return True
        return QtWidgets.QMessageBox.question(
            self, translate('SongFolderPlugin.MediaItem', 'Song Changed'),
            translate('SongFolderPlugin.MediaItem', 'The file {name} was changed on disk while you were editing '
                      'it. Do you want to overwrite the changes?').format(name=file_path)
        ) == QtWidgets.QMessageBox.StandardButton.Yes
