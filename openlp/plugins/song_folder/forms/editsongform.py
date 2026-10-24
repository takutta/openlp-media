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
The form to edit a song of the song folder. Unlike the edit form of the Songs plugin, it works on a :class:`FileSong`
and needs no database.
"""
import re
from typing import List, Optional

from PySide6 import QtWidgets

from openlp.core.common.i18n import UiStrings, translate
from openlp.core.lib.ui import create_button_box, critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.plugins.song_folder.lib.songfile import FileSong, SongVerse
from openlp.plugins.song_folder.lib.songwriter import split_names
from openlp.plugins.songs.lib import VerseType
from openlp.plugins.songs.lib.db import AuthorType


# A verse header in the lyrics editor, e.g. "---[Verse:1]---" or "---[Chorus:2a:fi]---"
VERSE_HEADER = re.compile(r'^---\[([^:\]]+):([^:\]]+)(?::([^\]]+))?\]---[ \t]*$', re.MULTILINE)
VERSE_LABEL = re.compile(r'^([0-9]+)([a-zA-Z]?)$')
# An entry of the verse order, e.g. "v1", "c", "v2a" or "kertosäe2"
ORDER_ENTRY = re.compile(r'([^\W\d_]+)([0-9]*)([a-z]?)')


def verse_names() -> List[str]:
    """
    The names of the verse types in the current language, in the order of ``VerseType.tags``
    """
    return [UiStrings().Verse, UiStrings().Chorus, UiStrings().Bridge, UiStrings().PreChorus, UiStrings().Intro,
            UiStrings().Ending, UiStrings().Other]


def verse_tag(name: str) -> str:
    """
    Find the verse tag for a verse type name in the current language or in English, e.g. "Kertosäe" or "Chorus"
    """
    name = name.strip().lower()
    for names in (verse_names(), VerseType.names):
        for index, verse_name in enumerate(names):
            if verse_name.lower() == name or (len(name) == 1 and verse_name[:1].lower() == name):
                return VerseType.tags[index]
    return VerseType.tags[VerseType.from_loose_input(name)]


def verses_to_text(verses: List[SongVerse]) -> str:
    """
    Turn verses into the text of the lyrics editor. Each verse starts with a header line like "---[Verse:1]---".
    """
    blocks = []
    for verse in verses:
        name = verse_names()[VerseType.from_tag(verse.tag)]
        label = verse.number + verse.part
        if verse.lang:
            label += ':' + verse.lang
        blocks.append('---[{name}:{label}]---\n{text}'.format(name=name, label=label, text=verse.text))
    return '\n'.join(blocks)


def text_to_verses(text: str) -> List[SongVerse]:
    """
    Read the verses from the text of the lyrics editor. Text before the first header becomes the first verse.
    Verse types are recognised in English and in the current language, and unknown ones become "Other".

    :raises ValueError: If a verse label is not a number with an optional letter, e.g. "2" or "2a"
    """
    verses = []
    parts = VERSE_HEADER.split(text)
    # split() gives the text before the first header, then (name, label, language, text) for each header
    if parts[0].strip():
        verses.append(SongVerse('v', '1', text=parts[0].strip('\n').rstrip()))
    for index in range(1, len(parts), 4):
        name, label, lang, verse_text = parts[index:index + 4]
        match = VERSE_LABEL.match(label.strip())
        if not match:
            raise ValueError(label)
        tag = verse_tag(name)
        verse_text = verse_text.strip('\n').rstrip()
        if verse_text:
            verses.append(SongVerse(tag, match.group(1), match.group(2).lower(), lang.strip() if lang else None,
                                    verse_text))
    return verses


def parse_verse_order(text: str) -> List[str]:
    """
    Read a verse order like "v1 c1 v2". The verse tags may also be given in the current language.
    """
    order = []
    for entry in text.lower().split():
        match = ORDER_ENTRY.fullmatch(entry)
        if not match:
            order.append(entry)
            continue
        tag, number, part = match.groups()
        if tag not in VerseType.tags:
            tag = verse_tag(tag)
        order.append(tag + number + part)
    return order


class EditSongForm(QtWidgets.QDialog):
    """
    Edit the properties and the lyrics of a song
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('song_folder_edit_song_form')
        self.resize(700, 750)
        layout = QtWidgets.QVBoxLayout(self)
        form_layout = QtWidgets.QFormLayout()
        layout.addLayout(form_layout)
        self.title_edit = QtWidgets.QLineEdit(self)
        self.title_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.title_label, self.title_edit)
        self.alternate_title_edit = QtWidgets.QLineEdit(self)
        self.alternate_title_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.alternate_title_label, self.alternate_title_edit)
        self.authors_table, authors_widget = self._create_table()
        self.authors_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.authors_label, authors_widget)
        self.copyright_edit = QtWidgets.QLineEdit(self)
        self.copyright_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.copyright_label, self.copyright_edit)
        self.ccli_edit = QtWidgets.QLineEdit(self)
        self.ccli_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.ccli_label, self.ccli_edit)
        self.songbooks_table, songbooks_widget = self._create_table()
        self.songbooks_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.songbooks_label, songbooks_widget)
        self.topics_edit = QtWidgets.QLineEdit(self)
        self.topics_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.topics_label, self.topics_edit)
        self.verse_order_edit = QtWidgets.QLineEdit(self)
        self.verse_order_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.verse_order_label, self.verse_order_edit)
        self.comments_edit = QtWidgets.QPlainTextEdit(self)
        self.comments_edit.setMaximumHeight(60)
        self.comments_label = QtWidgets.QLabel(self)
        form_layout.addRow(self.comments_label, self.comments_edit)
        self.lyrics_label = QtWidgets.QLabel(self)
        layout.addWidget(self.lyrics_label)
        self.lyrics_edit = QtWidgets.QPlainTextEdit(self)
        layout.addWidget(self.lyrics_edit, 1)
        self.lyrics_help_label = QtWidgets.QLabel(self)
        self.lyrics_help_label.setWordWrap(True)
        layout.addWidget(self.lyrics_help_label)
        self.button_box = create_button_box(self, 'button_box', ['cancel', 'save'])
        layout.addWidget(self.button_box)
        self.retranslate_ui()

    def _create_table(self):
        """
        Create a table with two columns and buttons to add and remove rows
        """
        widget = QtWidgets.QWidget(self)
        layout = QtWidgets.QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        table = QtWidgets.QTableWidget(0, 2, widget)
        table.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().hide()
        table.setMaximumHeight(100)
        layout.addWidget(table)
        buttons = QtWidgets.QVBoxLayout()
        add_button = QtWidgets.QToolButton(widget)
        add_button.setIcon(UiIcons().add)
        add_button.clicked.connect(lambda: self._add_row(table))
        remove_button = QtWidgets.QToolButton(widget)
        remove_button.setIcon(UiIcons().minus)
        remove_button.clicked.connect(lambda: table.removeRow(table.currentRow()))
        buttons.addWidget(add_button)
        buttons.addWidget(remove_button)
        buttons.addStretch()
        layout.addLayout(buttons)
        return table, widget

    def _add_row(self, table: QtWidgets.QTableWidget, first: str = '', second: str = '') -> int:
        """
        Add a row to the authors or the songbooks table. The type of an author is chosen from a list.
        """
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QtWidgets.QTableWidgetItem(first))
        if table is self.authors_table:
            combo = QtWidgets.QComboBox(table)
            for author_type in AuthorType.SortedTypes:
                combo.addItem(AuthorType.get_translated_type(author_type) or
                              translate('SongFolderPlugin.EditSongForm', 'Author'), author_type)
            combo.setCurrentIndex(max(combo.findData(second), 0))
            table.setCellWidget(row, 1, combo)
        else:
            table.setItem(row, 1, QtWidgets.QTableWidgetItem(second))
        if not first:
            table.setCurrentCell(row, 0)
            table.editItem(table.item(row, 0))
        return row

    def _table_rows(self, table: QtWidgets.QTableWidget) -> List[tuple]:
        """
        Return the non-empty rows of a table as (first column, second column) pairs
        """
        rows = []
        for row in range(table.rowCount()):
            first = table.item(row, 0).text().strip() if table.item(row, 0) else ''
            if table.cellWidget(row, 1):
                second = table.cellWidget(row, 1).currentData()
            else:
                second = table.item(row, 1).text().strip() if table.item(row, 1) else ''
            if first:
                rows.append((first, second))
        return rows

    def retranslate_ui(self):
        """
        Translate the form
        """
        self.title_label.setText(translate('SongFolderPlugin.EditSongForm', '&Title:'))
        self.title_label.setBuddy(self.title_edit)
        self.alternate_title_label.setText(translate('SongFolderPlugin.EditSongForm', 'Alt&ernate title:'))
        self.alternate_title_label.setBuddy(self.alternate_title_edit)
        self.authors_label.setText(translate('SongFolderPlugin.EditSongForm', 'Authors:'))
        self.authors_table.setHorizontalHeaderLabels([translate('SongFolderPlugin.EditSongForm', 'Name'),
                                                      translate('SongFolderPlugin.EditSongForm', 'Type')])
        self.copyright_label.setText(translate('SongFolderPlugin.EditSongForm', 'Copyright:'))
        self.ccli_label.setText(translate('SongFolderPlugin.EditSongForm', 'CCLI number:'))
        self.songbooks_label.setText(translate('SongFolderPlugin.EditSongForm', 'Songbooks:'))
        self.songbooks_table.setHorizontalHeaderLabels([translate('SongFolderPlugin.EditSongForm', 'Songbook'),
                                                        translate('SongFolderPlugin.EditSongForm', 'Number')])
        self.topics_label.setText(translate('SongFolderPlugin.EditSongForm', 'Topics:'))
        self.topics_edit.setPlaceholderText(translate('SongFolderPlugin.EditSongForm', 'Separated by commas'))
        self.verse_order_label.setText(translate('SongFolderPlugin.EditSongForm', '&Verse order:'))
        self.verse_order_label.setBuddy(self.verse_order_edit)
        self.verse_order_edit.setPlaceholderText(translate('SongFolderPlugin.EditSongForm', 'For example: v1 c1 v2 c1'))
        self.comments_label.setText(translate('SongFolderPlugin.EditSongForm', 'Comments:'))
        self.lyrics_label.setText(translate('SongFolderPlugin.EditSongForm', '&Lyrics:'))
        self.lyrics_label.setBuddy(self.lyrics_edit)
        self.lyrics_help_label.setText(translate(
            'SongFolderPlugin.EditSongForm',
            'Start each verse with a line like ---[Verse:1]--- or ---[Chorus:1]---. Use [---] for an optional split '
            'and [--}{--] for a page break. Chords are written in brackets, e.g. [G].'))

    def load_song(self, song: Optional[FileSong]):
        """
        Fill in the form

        :param song: The song to edit, or None for a new song
        """
        self.setWindowTitle(translate('SongFolderPlugin.EditSongForm', 'Song Editor'))
        song = song or FileSong()
        self.title_edit.setText(song.title)
        self.alternate_title_edit.setText(song.alternate_title)
        self.authors_table.setRowCount(0)
        for name, author_type in song.authors:
            self._add_row(self.authors_table, name, author_type)
        self.copyright_edit.setText(song.copyright)
        self.ccli_edit.setText(song.ccli_number)
        self.songbooks_table.setRowCount(0)
        for book, entry in song.songbooks:
            self._add_row(self.songbooks_table, book, entry)
        self.topics_edit.setText(', '.join(song.topics))
        self.verse_order_edit.setText(' '.join(song.verse_order))
        self.comments_edit.setPlainText(song.comments)
        if song.verses:
            self.lyrics_edit.setPlainText(verses_to_text(song.verses))
        else:
            self.lyrics_edit.setPlainText('---[{name}:1]---\n'.format(name=verse_names()[0]))
        self.title_edit.setFocus()

    def get_song(self) -> FileSong:
        """
        Read the song from the form

        :raises ValueError: If a verse label is not valid
        """
        titles = [self.title_edit.text().strip()]
        if self.alternate_title_edit.text().strip():
            titles.append(self.alternate_title_edit.text().strip())
        return FileSong(titles=titles,
                        authors=self._table_rows(self.authors_table),
                        copyright=self.copyright_edit.text().strip(),
                        ccli_number=self.ccli_edit.text().strip(),
                        comments=self.comments_edit.toPlainText().strip(),
                        songbooks=self._table_rows(self.songbooks_table),
                        topics=split_names(self.topics_edit.text()),
                        verse_order=parse_verse_order(self.verse_order_edit.text()),
                        verses=text_to_verses(self.lyrics_edit.toPlainText()))

    def validate(self) -> str:
        """
        Check the form

        :return: An error message, or an empty string if everything is fine
        """
        if not self.title_edit.text().strip():
            self.title_edit.setFocus()
            return translate('SongFolderPlugin.EditSongForm', 'You need to type in a song title.')
        try:
            song = self.get_song()
        except ValueError as error:
            self.lyrics_edit.setFocus()
            return translate('SongFolderPlugin.EditSongForm',
                             'The verse label "{label}" is not valid. Use a number, optionally followed by a letter, '
                             'for example 1 or 2a.').format(label=error)
        if not song.verses:
            self.lyrics_edit.setFocus()
            return translate('SongFolderPlugin.EditSongForm', 'You need to type in at least one verse.')
        names = {verse.name for verse in song.verses} | {verse.tag + verse.number for verse in song.verses} | \
            {verse.tag for verse in song.verses}
        missing = [entry for entry in song.verse_order if entry not in names]
        if missing:
            self.verse_order_edit.setFocus()
            return translate('SongFolderPlugin.EditSongForm',
                             'There are no verses matching "{entries}" in the verse order.'
                             ).format(entries=' '.join(missing))
        return ''

    def accept(self):
        """
        Close the form if the song is valid
        """
        error = self.validate()
        if error:
            critical_error_message_box(message=error)
            return
        super().accept()
