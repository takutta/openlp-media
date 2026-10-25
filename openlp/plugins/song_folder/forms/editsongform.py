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
The song editor of the Song Folder plugin. The editor of the Songs plugin is tied to its database, so this is a simpler
form which edits a :class:`FileSong`. The lyrics are edited as one text, with a ``---[Verse:1]---`` line before each
verse, like in the "Edit All" view of the Songs plugin.
"""
import re
from pathlib import Path
from typing import List, Optional, Tuple

from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common.i18n import UiStrings, get_natural_key, translate
from openlp.core.common.registry import Registry
from openlp.core.lib.ui import create_button_box, critical_error_message_box, find_and_set_in_combo_box
from openlp.core.ui.icons import UiIcons
from openlp.core.ui.media import get_supported_media_suffix
from openlp.core.widgets.dialogs import FileDialog
from openlp.plugins.songs.lib import VerseType, transpose_lyrics
from openlp.plugins.songs.lib.db import AuthorType
from openlp.plugins.songs.lib.ui import SongStrings, show_key_warning
from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse


VERSE_MARKER = re.compile(r'^---\[(?P<name>[^\]:]*)(?::(?P<number>[^\]:]*))?(?::(?P<lang>[^\]]*))?\]---[ \t]*$',
                          re.MULTILINE)
VERSE_NUMBER = re.compile(r'(\d+)([a-z]?)')
ORDER_ENTRY = re.compile(r'^(\D+?)(\d*)([a-z]?)$')


def verse_names() -> List[str]:
    """
    The translated names of the verse types, in the order of :class:`VerseType`
    """
    return [UiStrings().Verse, UiStrings().Chorus, UiStrings().Bridge, UiStrings().PreChorus, UiStrings().Intro,
            UiStrings().Ending, UiStrings().Other]


def verse_tag_from_name(name: str) -> str:
    """
    Find the verse tag ("v", "c" etc.) of a translated or English verse name, or of a translated or English tag

    :param name: The name, e.g. "Chorus", "c" or the translated name
    """
    name = name.strip().casefold()
    translated = [verse_name.casefold() for verse_name in verse_names()]
    english = [verse_name.casefold() for verse_name in VerseType.names]
    for names in (translated, english):
        if name in names:
            return VerseType.tags[names.index(name)]
    for names in (translated, english):
        for index, verse_name in enumerate(names):
            if name and verse_name.startswith(name):
                return VerseType.tags[index]
    return VerseType.tags[VerseType.Other]


def translated_tag(tag: str) -> str:
    """
    The translated upper case tag of a verse type, e.g. "V" for verses in English
    """
    return verse_names()[VerseType.tags.index(tag)][0].upper()


def lyrics_to_text(verses: List[SongVerse]) -> str:
    """
    Turn the verses of a song into the text that is edited

    :param verses: The verses
    """
    parts = []
    for verse in verses:
        marker = '{name}:{number}'.format(name=verse_names()[VerseType.tags.index(verse.tag)],
                                          number=verse.number + verse.part)
        if verse.lang:
            marker += ':' + verse.lang
        parts.append('---[{marker}]---\n{text}'.format(marker=marker, text=verse.text))
    return '\n'.join(parts)


def text_to_lyrics(text: str) -> List[SongVerse]:
    """
    Turn the edited text back into verses. Text before the first verse line becomes the first verse. Verses with the
    same name and language are joined, like they are when a file is read.

    :param text: The lyrics with ``---[Verse:1]---`` lines
    """
    text = text.replace('\r\n', '\n')
    verses = {}
    markers = list(VERSE_MARKER.finditer(text))
    chunks = [(None, text[:markers[0].start()] if markers else text)]
    for index, marker in enumerate(markers):
        end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
        chunks.append((marker, text[marker.end():end]))
    for marker, chunk in chunks:
        chunk = chunk.strip('\n').rstrip()
        if marker is None:
            if not chunk.strip():
                continue
            tag, number, part, lang = VerseType.tags[VerseType.Verse], '1', '', None
        else:
            tag = verse_tag_from_name(marker.group('name'))
            match = VERSE_NUMBER.search((marker.group('number') or '').strip().lower())
            number, part = (match.group(1), match.group(2)) if match else ('1', '')
            lang = (marker.group('lang') or '').strip() or None
        key = (tag, number, part, lang)
        if key in verses:
            verses[key].text += '\n' + chunk
        else:
            verses[key] = SongVerse(tag, number, part, lang, chunk)
    return [verse for verse in verses.values() if verse.text.strip()]


def order_to_text(verse_order: List[str]) -> str:
    """
    Show the verse order with translated tags, e.g. "V1 C V2"
    """
    entries = []
    for entry in verse_order:
        match = ORDER_ENTRY.match(entry)
        if match and match.group(1) in VerseType.tags:
            entries.append(translated_tag(match.group(1)) + match.group(2) + match.group(3))
        else:
            entries.append(entry)
    return ' '.join(entries)


def text_to_order(text: str) -> Tuple[List[str], List[str]]:
    """
    Turn the verse order typed by the user into tags

    :param text: The verse order, with translated or English tags
    :return: The verse order and the entries that could not be understood
    """
    order = []
    invalid = []
    translated = [name[0].casefold() for name in verse_names()]
    for entry in text.split():
        match = ORDER_ENTRY.match(entry.casefold())
        if not match:
            invalid.append(entry)
            continue
        letters = match.group(1)
        if len(letters) > 1:
            tag = verse_tag_from_name(letters)
        elif letters in translated:
            tag = VerseType.tags[translated.index(letters)]
        elif letters in VerseType.tags:
            tag = letters
        else:
            invalid.append(entry)
            continue
        order.append(tag + match.group(2) + match.group(3))
    return order, invalid


def invalid_order_entries(verse_order: List[str], verses: List[SongVerse]) -> List[str]:
    """
    Returns the entries of the verse order which do not match any verse, see :meth:`FileSong.ordered_verses`
    """
    return [entry for entry in verse_order
            if not any(entry in (verse.name, verse.tag + verse.number, verse.tag) for verse in verses)]


class SongFileEditForm(QtWidgets.QDialog):
    """
    Edits the song of an OpenLyrics file
    """
    def __init__(self, parent=None):
        super().__init__(parent, QtCore.Qt.WindowType.WindowSystemMenuHint | QtCore.Qt.WindowType.WindowTitleHint |
                         QtCore.Qt.WindowType.WindowCloseButtonHint)
        self.song: Optional[FileSong] = None
        self.audio_path: Optional[Path] = None
        # Where the audio file dialog starts when the song has no audio
        self.audio_folder: Optional[Path] = None
        self._other_titles: List[str] = []
        self.setup_ui()
        self.retranslate_ui()

    def setup_ui(self):
        self.setObjectName('song_file_edit_form')
        self.resize(700, 600)
        self.dialog_layout = QtWidgets.QVBoxLayout(self)
        self.tab_widget = QtWidgets.QTabWidget(self)
        self.dialog_layout.addWidget(self.tab_widget)
        # Title and lyrics
        self.lyrics_tab = QtWidgets.QWidget()
        self.lyrics_layout = QtWidgets.QGridLayout(self.lyrics_tab)
        self.title_label = QtWidgets.QLabel(self.lyrics_tab)
        self.title_edit = QtWidgets.QLineEdit(self.lyrics_tab)
        self.title_label.setBuddy(self.title_edit)
        self.lyrics_layout.addWidget(self.title_label, 0, 0)
        self.lyrics_layout.addWidget(self.title_edit, 0, 1)
        self.alternate_title_label = QtWidgets.QLabel(self.lyrics_tab)
        self.alternate_title_edit = QtWidgets.QLineEdit(self.lyrics_tab)
        self.alternate_title_label.setBuddy(self.alternate_title_edit)
        self.lyrics_layout.addWidget(self.alternate_title_label, 1, 0)
        self.lyrics_layout.addWidget(self.alternate_title_edit, 1, 1)
        self.lyrics_label = QtWidgets.QLabel(self.lyrics_tab)
        self.lyrics_layout.addWidget(self.lyrics_label, 2, 0, QtCore.Qt.AlignmentFlag.AlignTop)
        self.lyrics_edit = QtWidgets.QPlainTextEdit(self.lyrics_tab)
        self.lyrics_edit.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.NoWrap)
        self.lyrics_label.setBuddy(self.lyrics_edit)
        self.lyrics_layout.addWidget(self.lyrics_edit, 2, 1)
        self.insert_layout = QtWidgets.QHBoxLayout()
        self.verse_type_combo_box = QtWidgets.QComboBox(self.lyrics_tab)
        self.verse_type_combo_box.addItems([''] * len(VerseType.names))
        self.insert_layout.addWidget(self.verse_type_combo_box)
        self.insert_button = QtWidgets.QPushButton(self.lyrics_tab)
        self.insert_button.setIcon(UiIcons().add)
        self.insert_layout.addWidget(self.insert_button)
        self.split_button = QtWidgets.QPushButton(self.lyrics_tab)
        self.insert_layout.addWidget(self.split_button)
        self.forced_split_button = QtWidgets.QPushButton(self.lyrics_tab)
        self.insert_layout.addWidget(self.forced_split_button)
        self.insert_layout.addStretch()
        self.transpose_widget = QtWidgets.QWidget(self.lyrics_tab)
        self.transpose_layout = QtWidgets.QHBoxLayout(self.transpose_widget)
        self.transpose_layout.setContentsMargins(0, 0, 0, 0)
        self.transpose_label = QtWidgets.QLabel(self.transpose_widget)
        self.transpose_layout.addWidget(self.transpose_label)
        self.transpose_up_button = QtWidgets.QPushButton(self.transpose_widget)
        self.transpose_up_button.setIcon(UiIcons().arrow_up)
        self.transpose_layout.addWidget(self.transpose_up_button)
        self.transpose_down_button = QtWidgets.QPushButton(self.transpose_widget)
        self.transpose_down_button.setIcon(UiIcons().arrow_down)
        self.transpose_layout.addWidget(self.transpose_down_button)
        self.insert_layout.addWidget(self.transpose_widget)
        self.lyrics_layout.addLayout(self.insert_layout, 3, 1)
        self.verse_order_label = QtWidgets.QLabel(self.lyrics_tab)
        self.verse_order_edit = QtWidgets.QLineEdit(self.lyrics_tab)
        self.verse_order_label.setBuddy(self.verse_order_edit)
        self.lyrics_layout.addWidget(self.verse_order_label, 4, 0)
        self.lyrics_layout.addWidget(self.verse_order_edit, 4, 1)
        self.tab_widget.addTab(self.lyrics_tab, '')
        # Authors, topics and songbooks
        self.authors_tab = QtWidgets.QWidget()
        self.authors_tab_layout = QtWidgets.QVBoxLayout(self.authors_tab)
        self.authors_group_box = QtWidgets.QGroupBox(self.authors_tab)
        self.authors_layout = QtWidgets.QGridLayout(self.authors_group_box)
        self.author_name_edit = QtWidgets.QLineEdit(self.authors_group_box)
        self.authors_layout.addWidget(self.author_name_edit, 0, 0)
        self.author_type_combo_box = QtWidgets.QComboBox(self.authors_group_box)
        self.author_type_combo_box.addItems([''] * len(AuthorType.SortedTypes))
        self.authors_layout.addWidget(self.author_type_combo_box, 0, 1)
        self.author_add_button = QtWidgets.QPushButton(self.authors_group_box)
        self.authors_layout.addWidget(self.author_add_button, 0, 2)
        self.authors_list_view = QtWidgets.QTreeWidget(self.authors_group_box)
        self.authors_list_view.setColumnCount(2)
        self.authors_list_view.setRootIsDecorated(False)
        self.authors_list_view.setHeaderHidden(True)
        self.authors_layout.addWidget(self.authors_list_view, 1, 0, 1, 2)
        self.author_remove_button = QtWidgets.QPushButton(self.authors_group_box)
        self.authors_layout.addWidget(self.author_remove_button, 1, 2, QtCore.Qt.AlignmentFlag.AlignTop)
        self.authors_tab_layout.addWidget(self.authors_group_box)
        self.topics_group_box = QtWidgets.QGroupBox(self.authors_tab)
        self.topics_layout = QtWidgets.QVBoxLayout(self.topics_group_box)
        self.topics_edit = QtWidgets.QPlainTextEdit(self.topics_group_box)
        self.topics_layout.addWidget(self.topics_edit)
        self.authors_tab_layout.addWidget(self.topics_group_box)
        self.songbooks_group_box = QtWidgets.QGroupBox(self.authors_tab)
        self.songbooks_layout = QtWidgets.QVBoxLayout(self.songbooks_group_box)
        self.songbooks_edit = QtWidgets.QPlainTextEdit(self.songbooks_group_box)
        self.songbooks_layout.addWidget(self.songbooks_edit)
        self.authors_tab_layout.addWidget(self.songbooks_group_box)
        self.tab_widget.addTab(self.authors_tab, '')
        # Copyright and comments
        self.rights_tab = QtWidgets.QWidget()
        self.rights_tab_layout = QtWidgets.QVBoxLayout(self.rights_tab)
        self.theme_group_box = QtWidgets.QGroupBox(self.rights_tab)
        self.theme_layout = QtWidgets.QHBoxLayout(self.theme_group_box)
        self.theme_combo_box = QtWidgets.QComboBox(self.theme_group_box)
        self.theme_combo_box.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.theme_combo_box.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                           QtWidgets.QSizePolicy.Policy.Fixed)
        self.theme_layout.addWidget(self.theme_combo_box)
        self.rights_tab_layout.addWidget(self.theme_group_box)
        self.rights_group_box = QtWidgets.QGroupBox(self.rights_tab)
        self.rights_layout = QtWidgets.QGridLayout(self.rights_group_box)
        self.copyright_edit = QtWidgets.QLineEdit(self.rights_group_box)
        self.rights_layout.addWidget(self.copyright_edit, 0, 0, 1, 2)
        self.copyright_insert_button = QtWidgets.QToolButton(self.rights_group_box)
        self.rights_layout.addWidget(self.copyright_insert_button, 0, 2)
        self.ccli_label = QtWidgets.QLabel(self.rights_group_box)
        self.ccli_number_edit = QtWidgets.QLineEdit(self.rights_group_box)
        self.ccli_number_edit.setValidator(QtGui.QIntValidator(self.ccli_number_edit))
        self.ccli_label.setBuddy(self.ccli_number_edit)
        self.rights_layout.addWidget(self.ccli_label, 1, 0)
        self.rights_layout.addWidget(self.ccli_number_edit, 1, 1, 1, 2)
        self.rights_tab_layout.addWidget(self.rights_group_box)
        self.comments_group_box = QtWidgets.QGroupBox(self.rights_tab)
        self.comments_layout = QtWidgets.QVBoxLayout(self.comments_group_box)
        self.comments_edit = QtWidgets.QPlainTextEdit(self.comments_group_box)
        self.comments_layout.addWidget(self.comments_edit)
        self.rights_tab_layout.addWidget(self.comments_group_box)
        self.tab_widget.addTab(self.rights_tab, '')
        # Background audio
        self.audio_tab = QtWidgets.QWidget()
        self.audio_tab_layout = QtWidgets.QVBoxLayout(self.audio_tab)
        self.audio_layout = QtWidgets.QHBoxLayout()
        self.audio_edit = QtWidgets.QLineEdit(self.audio_tab)
        self.audio_edit.setReadOnly(True)
        self.audio_layout.addWidget(self.audio_edit)
        self.audio_choose_button = QtWidgets.QPushButton(self.audio_tab)
        self.audio_choose_button.setIcon(UiIcons().open)
        self.audio_layout.addWidget(self.audio_choose_button)
        self.audio_remove_button = QtWidgets.QPushButton(self.audio_tab)
        self.audio_remove_button.setIcon(UiIcons().delete)
        self.audio_layout.addWidget(self.audio_remove_button)
        self.audio_tab_layout.addLayout(self.audio_layout)
        self.audio_help_label = QtWidgets.QLabel(self.audio_tab)
        self.audio_help_label.setWordWrap(True)
        self.audio_tab_layout.addWidget(self.audio_help_label)
        self.audio_tab_layout.addStretch()
        self.tab_widget.addTab(self.audio_tab, '')
        self.button_box = create_button_box(self, 'button_box', ['cancel', 'save'])
        self.dialog_layout.addWidget(self.button_box)
        # Signals and slots
        self.insert_button.clicked.connect(self.on_insert_button_clicked)
        self.split_button.clicked.connect(lambda: self.insert_text('[---]'))
        self.forced_split_button.clicked.connect(lambda: self.insert_text('[--}{--]'))
        self.author_add_button.clicked.connect(self.on_author_add_button_clicked)
        self.author_name_edit.returnPressed.connect(self.on_author_add_button_clicked)
        self.author_remove_button.clicked.connect(self.on_author_remove_button_clicked)
        self.copyright_insert_button.clicked.connect(self.on_copyright_insert_button_clicked)
        self.transpose_up_button.clicked.connect(lambda: self.transpose(1))
        self.transpose_down_button.clicked.connect(lambda: self.transpose(-1))
        self.audio_choose_button.clicked.connect(self.on_audio_choose_button_clicked)
        self.audio_remove_button.clicked.connect(lambda: self.set_audio_path(None))
        Registry().register_function('theme_update_list', self.load_themes)

    def retranslate_ui(self):
        self.setWindowTitle(translate('SongsPlugin.EditSongForm', 'Song Editor'))
        self.title_label.setText(translate('SongsPlugin.EditSongForm', '&Title:'))
        self.alternate_title_label.setText(translate('SongsPlugin.EditSongForm', 'Alt&ernate title:'))
        self.lyrics_label.setText(translate('SongsPlugin.EditSongForm', '&Lyrics:'))
        self.lyrics_edit.setToolTip(translate('SongFolderPlugin.EditSongForm',
                                              'Start each verse with a line like ---[{verse}:1]---.'
                                              ).format(verse=UiStrings().Verse))
        self.verse_order_label.setText(translate('SongsPlugin.EditSongForm', '&Verse order:'))
        for index, name in enumerate(verse_names()):
            self.verse_type_combo_box.setItemText(index, name)
        self.insert_button.setText(UiStrings().Insert)
        self.insert_button.setToolTip(UiStrings().InsertToolTip)
        self.split_button.setText(UiStrings().Split)
        self.split_button.setToolTip(UiStrings().SplitToolTip)
        self.forced_split_button.setText(UiStrings().ForcedSplit)
        self.forced_split_button.setToolTip(UiStrings().ForcedSplitToolTip)
        self.transpose_label.setText(UiStrings().Transpose)
        self.transpose_up_button.setText(UiStrings().Up)
        self.transpose_down_button.setText(UiStrings().Down)
        self.theme_group_box.setTitle(UiStrings().Theme)
        if self.theme_combo_box.count():
            self.theme_combo_box.setItemText(0, '<{default}>'.format(default=UiStrings().Default))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.lyrics_tab),
                                   translate('SongsPlugin.EditSongForm', 'Title && Lyrics'))
        self.authors_group_box.setTitle(SongStrings().Authors)
        for index, author_type in enumerate(AuthorType.SortedTypes):
            self.author_type_combo_box.setItemText(index, AuthorType.get_translated_type(author_type))
        self.author_add_button.setText(translate('SongsPlugin.EditSongForm', '&Add to Song'))
        self.author_remove_button.setText(translate('SongsPlugin.EditSongForm', '&Remove'))
        self.topics_group_box.setTitle(SongStrings().Topics)
        self.topics_edit.setPlaceholderText(translate('SongFolderPlugin.EditSongForm', 'One topic per line'))
        self.songbooks_group_box.setTitle(SongStrings().SongBooks)
        self.songbooks_edit.setPlaceholderText(translate('SongFolderPlugin.EditSongForm',
                                                         'One songbook per line, e.g. "Hymnal #123"'))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.authors_tab),
                                   translate('SongsPlugin.EditSongForm', 'Authors, Topics && Songbooks'))
        self.rights_group_box.setTitle(translate('SongsPlugin.EditSongForm', 'Copyright Information'))
        self.copyright_insert_button.setText(SongStrings().CopyrightSymbol)
        self.ccli_label.setText(UiStrings().CCLISongNumberLabel)
        self.comments_group_box.setTitle(translate('SongsPlugin.EditSongForm', 'Comments'))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.rights_tab),
                                   translate('SongFolderPlugin.EditSongForm', 'Theme, Copyright && Comments'))
        self.audio_choose_button.setText(translate('SongFolderPlugin.EditSongForm', '&Choose File...'))
        self.audio_remove_button.setText(translate('SongsPlugin.EditSongForm', '&Remove'))
        self.audio_edit.setPlaceholderText(translate('SongFolderPlugin.EditSongForm', 'No background audio'))
        self.audio_help_label.setText(translate('SongFolderPlugin.EditSongForm',
                                                'The audio file is copied next to the song file, with the same name '
                                                'as the song file. It is moved and deleted together with the song.'))
        self.tab_widget.setTabText(self.tab_widget.indexOf(self.audio_tab),
                                   translate('SongsPlugin.EditSongForm', 'Linked Audio'))

    # Loading and saving

    def load_song(self, song: Optional[FileSong], audio_path: Optional[Path] = None):
        """
        Show a song in the form

        :param song: The song to edit, or None for a new song
        :param audio_path: The background audio file of the song, if it has one
        """
        song = song or FileSong()
        self.song = None
        self.tab_widget.setCurrentIndex(0)
        self._other_titles = song.titles[2:]
        self.title_edit.setText(song.title)
        self.alternate_title_edit.setText(song.alternate_title)
        if song.verses:
            self.lyrics_edit.setPlainText(lyrics_to_text(song.verses))
        else:
            self.lyrics_edit.setPlainText('---[{verse}:1]---\n'.format(verse=UiStrings().Verse))
        self.verse_order_edit.setText(order_to_text(song.verse_order))
        self.authors_list_view.clear()
        for name, author_type in song.authors:
            self.add_author(name, author_type)
        self.topics_edit.setPlainText('\n'.join(song.topics))
        self.songbooks_edit.setPlainText('\n'.join(song.songbook_entries))
        self.copyright_edit.setText(song.copyright)
        self.ccli_number_edit.setText(song.ccli_number)
        self.comments_edit.setPlainText(song.comments)
        if not self.theme_combo_box.count():
            theme_manager = Registry().get('theme_manager') if 'theme_manager' in Registry().service_list else None
            self.load_themes(theme_manager.get_theme_names() if theme_manager else [])
        if song.theme:
            find_and_set_in_combo_box(self.theme_combo_box, song.theme)
        else:
            self.theme_combo_box.setCurrentIndex(0)
        self.transpose_widget.setVisible(bool(Registry().get('settings').value('songs/enable chords')))
        self.set_audio_path(audio_path)
        self.title_edit.setFocus()

    def get_song(self) -> FileSong:
        """
        Returns the song in the form, without checking it
        """
        song = FileSong()
        song.titles = [self.title_edit.text().strip(), self.alternate_title_edit.text().strip()] + self._other_titles
        while song.titles and not song.titles[-1]:
            song.titles.pop()
        song.verses = text_to_lyrics(self.lyrics_edit.toPlainText())
        song.verse_order, _ = text_to_order(self.verse_order_edit.text())
        song.authors = [(item.data(0, QtCore.Qt.ItemDataRole.UserRole), item.data(1, QtCore.Qt.ItemDataRole.UserRole))
                        for item in self._author_items()]
        song.topics = [line.strip() for line in self.topics_edit.toPlainText().split('\n') if line.strip()]
        song.songbooks = []
        for line in self.songbooks_edit.toPlainText().split('\n'):
            book, separator, entry = line.strip().rpartition(' #')
            if not separator:
                book, entry = line.strip(), ''
            if book.strip():
                song.songbooks.append((book.strip(), entry.strip()))
        song.copyright = self.copyright_edit.text().strip()
        song.ccli_number = self.ccli_number_edit.text().strip()
        song.comments = self.comments_edit.toPlainText().strip()
        song.theme = self.theme_combo_box.currentText() if self.theme_combo_box.currentIndex() > 0 else ''
        return song

    def validate(self) -> bool:
        """
        Check the song and tell the user what is wrong with it
        """
        if not self.title_edit.text().strip():
            self.tab_widget.setCurrentIndex(0)
            self.title_edit.setFocus()
            critical_error_message_box(
                message=translate('SongsPlugin.EditSongForm', 'You need to type in a song title.'))
            return False
        verses = text_to_lyrics(self.lyrics_edit.toPlainText())
        if not verses:
            self.tab_widget.setCurrentIndex(0)
            self.lyrics_edit.setFocus()
            critical_error_message_box(
                message=translate('SongsPlugin.EditSongForm', 'You need to type in at least one verse.'))
            return False
        verse_order, invalid = text_to_order(self.verse_order_edit.text())
        invalid += invalid_order_entries(verse_order, verses)
        if invalid:
            self.tab_widget.setCurrentIndex(0)
            self.verse_order_edit.setFocus()
            valid = ', '.join(translated_tag(verse.tag) + verse.number + verse.part for verse in verses)
            invalid = ', '.join(order_to_text([entry]) for entry in invalid)
            critical_error_message_box(
                title=translate('SongsPlugin.EditSongForm', 'Invalid Verse Order'),
                message=translate('SongsPlugin.EditSongForm',
                                  'There are no verses corresponding to "{invalid}". Valid entries are {valid}.\n'
                                  'Please enter the verses separated by spaces.').format(invalid=invalid, valid=valid))
            return False
        return True

    def accept(self):
        """
        Check the song before closing the form
        """
        if not self.validate():
            return
        self.song = self.get_song()
        super().accept()

    # Editing

    def insert_text(self, text: str):
        """
        Insert text on a line of its own at the cursor of the lyrics
        """
        cursor = self.lyrics_edit.textCursor()
        if cursor.positionInBlock() > 0:
            cursor.movePosition(QtGui.QTextCursor.MoveOperation.EndOfBlock)
            text = '\n' + text
            if cursor.atEnd():
                text += '\n'
        else:
            text += '\n'
        cursor.insertText(text)
        self.lyrics_edit.setTextCursor(cursor)
        self.lyrics_edit.setFocus()

    def on_insert_button_clicked(self):
        """
        Insert the line that starts a new verse. The verse gets the next free number of its type.
        """
        tag = VerseType.tags[self.verse_type_combo_box.currentIndex()]
        numbers = [int(verse.number) for verse in text_to_lyrics(self.lyrics_edit.toPlainText())
                   if verse.tag == tag and verse.number.isdigit()]
        self.insert_text('---[{name}:{number}]---'.format(name=self.verse_type_combo_box.currentText(),
                                                          number=max(numbers, default=0) + 1))

    def _author_items(self) -> List[QtWidgets.QTreeWidgetItem]:
        return [self.authors_list_view.topLevelItem(index)
                for index in range(self.authors_list_view.topLevelItemCount())]

    def add_author(self, name: str, author_type: str = AuthorType.NoType):
        """
        Add an author to the list, unless they are in it already
        """
        if any(item.data(0, QtCore.Qt.ItemDataRole.UserRole) == name and
               item.data(1, QtCore.Qt.ItemDataRole.UserRole) == author_type for item in self._author_items()):
            return
        item = QtWidgets.QTreeWidgetItem([name, AuthorType.get_translated_type(author_type)])
        item.setData(0, QtCore.Qt.ItemDataRole.UserRole, name)
        item.setData(1, QtCore.Qt.ItemDataRole.UserRole, author_type)
        self.authors_list_view.addTopLevelItem(item)

    def on_author_add_button_clicked(self):
        name = self.author_name_edit.text().strip()
        if not name:
            return
        self.add_author(name, AuthorType.SortedTypes[self.author_type_combo_box.currentIndex()])
        self.author_name_edit.clear()

    def on_author_remove_button_clicked(self):
        for item in self.authors_list_view.selectedItems():
            self.authors_list_view.takeTopLevelItem(self.authors_list_view.indexOfTopLevelItem(item))

    def load_themes(self, theme_list: List[str]):
        """
        Fill the theme list, with the default theme first. Called by the theme manager when the themes change.

        :param theme_list: The names of the themes
        """
        current = self.theme_combo_box.currentText() if self.theme_combo_box.currentIndex() > 0 else ''
        self.theme_combo_box.clear()
        self.theme_combo_box.addItem('<{default}>'.format(default=UiStrings().Default))
        self.theme_combo_box.addItems(sorted(theme_list, key=get_natural_key))
        if current:
            find_and_set_in_combo_box(self.theme_combo_box, current)

    def transpose(self, steps: int):
        """
        Transpose the chords of the lyrics, like the verse editor of the Songs plugin

        :param steps: Half steps up (positive) or down (negative)
        """
        text = self.lyrics_edit.toPlainText()
        chords = re.findall(r'\[(.*?)\]', re.sub(r'---\[.*?\]---|\[---\]|\[--}{--\]', '\n', text))
        if chords and not chords[0].startswith('='):
            show_key_warning(self)
        try:
            self.lyrics_edit.setPlainText(transpose_lyrics(text, steps))
        except KeyError as error:
            critical_error_message_box(title=translate('SongsPlugin.EditVerseForm', 'Transposing failed'),
                                       message=translate('SongsPlugin.EditVerseForm',
                                                         'Transposing failed because of invalid chord:\n{err_msg}'
                                                         ).format(err_msg=error))

    def set_audio_path(self, audio_path: Optional[Path]):
        """
        Show the background audio file of the song

        :param audio_path: The audio file, or None for no background audio
        """
        self.audio_path = audio_path
        self.audio_edit.setText(str(audio_path) if audio_path else '')
        self.audio_edit.setToolTip(str(audio_path) if audio_path else '')
        self.audio_remove_button.setEnabled(audio_path is not None)

    def on_audio_choose_button_clicked(self):
        """
        Choose an audio file to play in the background of the song
        """
        audio, _ = get_supported_media_suffix()
        filters = '{audio} ({suffixes})'.format(audio=translate('SongFolderPlugin.EditSongForm', 'Audio Files'),
                                                suffixes=' '.join(suffix for suffix in audio if suffix))
        file_path, _ = FileDialog.getOpenFileName(self, translate('SongFolderPlugin.EditSongForm',
                                                                  'Choose Background Audio'),
                                                  self.audio_path.parent if self.audio_path else self.audio_folder,
                                                  filters)
        if file_path:
            self.set_audio_path(file_path)

    def on_copyright_insert_button_clicked(self):
        self.copyright_edit.insert(SongStrings().CopyrightSymbol)
        self.copyright_edit.setFocus()
