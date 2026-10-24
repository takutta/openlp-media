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
import logging
from collections import namedtuple
from pathlib import Path
from typing import Any, List, Optional

import mako.exceptions
import mako.template
from PySide6 import QtCore, QtWidgets

from openlp.core.common.i18n import UiStrings, translate
from openlp.core.lib import ServiceItemContext, check_item_selected, create_separated_list
from openlp.core.lib.plugin import StringContent
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import create_widget_action, critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole
from openlp.plugins.song_folder.forms.editsongform import EditSongForm
from openlp.plugins.song_folder.lib.songfile import FORCED_SPLIT, FileSong, SongFileError
from openlp.plugins.song_folder.lib.songindex import SongIndex
from openlp.plugins.song_folder.lib.songwriter import song_file_name, write_song_file
from openlp.plugins.songs.lib import VerseType
from openlp.plugins.songs.lib.db import AuthorType
from openlp.plugins.songs.lib.ui import SongStrings


log = logging.getLogger(__name__)

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
    log.info('{name} SongFolderMediaItem loaded'.format(name=__name__))

    def __init__(self, parent, plugin):
        self.index = SongIndex()
        super().__init__(parent, plugin)

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

    def required_icons(self):
        """
        Songs can be created and edited
        """
        super().required_icons()
        self.has_new_icon = True
        self.has_edit_icon = True

    def add_custom_context_actions(self):
        """
        Add "Edit" to the context menu
        """
        create_widget_action(self.list_view, separator=True)
        create_widget_action(self.list_view, text=self.plugin.get_string(StringContent.Edit)['title'],
                             icon=UiIcons().edit, triggers=self.on_edit_click)

    def setup_item(self):
        """
        Do some additional setup
        """
        self.edit_song_form = EditSongForm(self)
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
        self.filter_list(self.search_text_edit.displayText())

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
        song = self.index.get(file_path)
        if song is None:
            if not remote:
                critical_error_message_box(
                    translate('SongFolderPlugin.MediaItem', 'Could not read the song'),
                    translate('SongFolderPlugin.MediaItem', 'The file {name} could not be read as an OpenLyrics '
                              'song:\n{error}').format(name=file_path, error=self.index.error(file_path) or
                                                       translate('SongFolderPlugin.MediaItem', 'File not found.')))
            return False
        service_item.title = song.title
        service_item.add_capability(ItemCapabilities.CanPreview)
        service_item.add_capability(ItemCapabilities.CanLoop)
        service_item.add_capability(ItemCapabilities.CanSoftBreak)
        service_item.add_capability(ItemCapabilities.OnLoadUpdate)
        service_item.add_capability(ItemCapabilities.CanEdit)
        service_item.edit_id = str(file_path)
        for verse in song.ordered_verses():
            verse_def = '{tag}{number}'.format(tag=VerseType.translated_tag(verse.tag), number=verse.number)
            for page in FORCED_SPLIT.split(verse.text):
                service_item.add_from_text(page, verse_def)
        authors = get_authors(song)
        self.generate_footer(service_item, song, authors)
        service_item.data_string = {
            'title': song.title,
            'alternate_title': song.alternate_title,
            'authors': ', '.join(authors.all),
            'ccli_number': song.ccli_number,
            'copyright': song.copyright,
            'file path': str(file_path)
        }
        # The core only knows the icons of its own plugins
        service_item.icon = UiIcons().music
        return True

    def generate_footer(self, service_item, song: FileSong, authors: Authors):
        """
        Build the footer with the footer template of the Songs plugin, so that both plugins show songs the same way

        :param service_item: The service item to be amended
        :param song: The song
        :param authors: The authors of the song
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
        try:
            footer_template = self.settings.value('songs/footer template')
            service_item.footer_html = mako.template.Template(footer_template).render_unicode(**footer_vars) \
                .replace('\n', '')
        except (mako.exceptions.SyntaxException, mako.exceptions.CompileException):
            # The plain footer is used instead
            log.error('Failed to render Song footer html:\n' + mako.exceptions.text_error_template().render())

    def service_load(self, item):
        """
        Set the icon of a service item that was loaded from a service file. If the song file is still there, the item
        can be edited again.

        :param item: The service item that was loaded
        """
        item.icon = UiIcons().music
        file_path = (item.data_string or {}).get('file path') if isinstance(item.data_string, dict) else None
        if file_path and Path(file_path).is_file():
            item.edit_id = file_path
        elif item.is_capable(ItemCapabilities.CanEdit):
            item.remove_capability(ItemCapabilities.CanEdit)
        return item

    # Editing songs

    def _save_song(self, song: FileSong, file_path: Path, keep_contents: bool) -> bool:
        """
        Write a song to its file, showing an error if it fails
        """
        try:
            write_song_file(song, file_path, keep_contents)
        except SongFileError as error:
            critical_error_message_box(
                translate('SongFolderPlugin.MediaItem', 'Could not save the song'),
                translate('SongFolderPlugin.MediaItem', 'The song could not be saved to {name}:\n{error}'
                          ).format(name=file_path, error=error))
            return False
        return True

    def edit_song_file(self, file_path: Path) -> bool:
        """
        Edit the song in a file and save it to the same file. The file name stays the same even if the title changes.

        :param file_path: The song file
        :return: True if the song was saved
        """
        song = self.index.get(file_path)
        if song is None:
            critical_error_message_box(
                translate('SongFolderPlugin.MediaItem', 'Could not read the song'),
                translate('SongFolderPlugin.MediaItem', 'The file {name} could not be read as an OpenLyrics '
                          'song:\n{error}').format(name=file_path, error=self.index.error(file_path) or
                                                   translate('SongFolderPlugin.MediaItem', 'File not found.')))
            return False
        self.edit_song_form.load_song(song)
        if self.edit_song_form.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return False
        if not self._save_song(self.edit_song_form.get_song(), file_path, keep_contents=True):
            return False
        self.reload(select_paths=[file_path])
        return True

    def on_new_click(self):
        """
        Create a new song file in the current folder
        """
        if not self._require_root():
            return
        self.edit_song_form.load_song(None)
        if self.edit_song_form.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        song = self.edit_song_form.get_song()
        file_path = song_file_name(song.title, self.current_folder)
        if self._save_song(song, file_path, keep_contents=False):
            self.reload(select_paths=[file_path])

    def on_edit_click(self):
        """
        Edit the selected song. The songs in the service are updated too.
        """
        if not check_item_selected(self.list_view, UiStrings().SelectEdit):
            return
        tree_item = self.list_view.currentItem() or self.list_view.selectedItems()[0]
        if tree_item.data(0, ItemTypeRole) != ItemType.File:
            return
        file_path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if self.edit_song_file(file_path):
            self.update_service_items(file_path)

    def update_service_items(self, file_path: Path):
        """
        Update the copies of a song in the service after the file has been edited

        :param file_path: The song file
        """
        service_manager = self.service_manager
        if not any(item['service_item'].name == self.plugin.name and item['service_item'].edit_id == str(file_path)
                   for item in service_manager.service_items):
            return
        new_item = self.build_service_item(self.create_item_from_id(file_path), remote=True)
        if new_item:
            service_manager.replace_service_item(new_item)

    def on_remote_edit(self, edit_id: str, preview: bool = False):
        """
        Edit a song from the service or the slide controller

        :param edit_id: The path of the song file
        :param preview: Is the song edited from the preview
        :return: The new service item, or None if nothing was changed
        """
        file_path = Path(edit_id)
        if not self.edit_song_file(file_path):
            return None
        item = self.build_service_item(self.create_item_from_id(file_path), remote=True)
        if item and preview:
            # A song can only be edited if it comes from the plugin, so it is set again for the new item
            item.from_plugin = True
        return item
