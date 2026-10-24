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
from openlp.core.lib import ServiceItemContext, create_separated_list
from openlp.core.lib.serviceitem import ItemCapabilities
from openlp.core.lib.ui import critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.plugins.filesystem_library.libraryitem import FileSystemLibraryItem, ItemType, ItemTypeRole
from openlp.plugins.song_folder.lib.songfile import FORCED_SPLIT, FileSong
from openlp.plugins.song_folder.lib.songindex import SongIndex
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
    song_folder_go_live = QtCore.Signal(list)
    song_folder_add_to_service = QtCore.Signal(list)
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
        Set the icon of a service item that was loaded from a service file

        :param item: The service item that was loaded
        """
        item.icon = UiIcons().music
        return item
