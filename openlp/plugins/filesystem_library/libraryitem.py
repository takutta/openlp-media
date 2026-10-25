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
Provides a library base class which shows the contents of a folder on disk instead of the contents of a database
"""
import os
import shutil
from pathlib import Path
from typing import Any, Iterator, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

from openlp.core.common.i18n import UiStrings, get_natural_key, translate
from openlp.core.common.settings import Settings
from openlp.core.lib import check_item_selected
from openlp.core.lib.mediamanageritem import MediaManagerItem
from openlp.core.lib.plugin import StringContent
from openlp.core.lib.ui import create_widget_action, critical_error_message_box
from openlp.core.ui.icons import UiIcons
from openlp.core.widgets.dialogs import FileDialog
from openlp.core.widgets.views import TreeWidgetWithDnD


# Extra role used to tell folders and files apart without hitting the disk
ItemTypeRole = QtCore.Qt.ItemDataRole.UserRole + 1


class ItemType(object):
    Folder = 'folder'
    File = 'file'


def move_to_trash(path: Path) -> bool:
    """
    Move a file or folder to the trash of the operating system

    :param path: The file or folder to move
    :return: True if it succeeded
    """
    result = QtCore.QFile.moveToTrash(str(path))
    # Depending on the PySide6 version, a tuple of (success, path in trash) might be returned
    if isinstance(result, tuple):
        result = result[0]
    return bool(result)


class FileSystemLibraryItem(MediaManagerItem):
    """
    A MediaManagerItem which lists the files of a root folder on disk. Folders in the library are real folders and
    items are real files, so nothing needs to be stored in a database. The library is refreshed automatically when the
    contents of the folder change on disk.

    Descendant classes need to implement :meth:`is_supported_file` and :meth:`generate_slide_data`, and can override
    :meth:`load_item` to customise how a file is shown.
    """
    def __init__(self, parent, plugin):
        self._watcher = QtCore.QFileSystemWatcher()
        self._reload_timer = QtCore.QTimer()
        self._reload_timer.setSingleShot(True)
        self._reload_timer.setInterval(500)
        self._file_paths: List[Path] = []
        super().__init__(parent, plugin)
        self._watcher.directoryChanged.connect(self.on_directory_changed)
        self._reload_timer.timeout.connect(self.on_refresh_click)

    @property
    def root_path(self) -> Optional[Path]:
        """
        The folder which is shown in the library, or None if it has not been set or does not exist
        """
        root_path = self.settings.value(self.settings_section + '/root folder')
        if root_path and Path(root_path).is_dir():
            return Path(root_path)
        return None

    @root_path.setter
    def root_path(self, path: Optional[Path]):
        self.settings.setValue(self.settings_section + '/root folder', path)
        self.reload()

    @property
    def current_folder(self) -> Optional[Path]:
        """
        Returns the folder of the selected item, or the root folder if nothing is selected
        """
        selected_items = self.list_view.selectedItems()
        if selected_items:
            tree_item = selected_items[0]
            path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if tree_item.data(0, ItemTypeRole) == ItemType.Folder:
                return path
            elif isinstance(path, Path):
                return path.parent
        return self.root_path

    def required_icons(self):
        """
        Set which icons the media manager tab should show
        """
        super().required_icons()
        self.has_file_icon = True
        self.has_new_icon = False
        self.has_edit_icon = False

    def retranslate_ui(self):
        """
        Translate the toolbar actions
        """
        self.choose_root_action.setText(translate('OpenLP.FileSystemLibraryItem', 'Choose folder'))
        self.choose_root_action.setToolTip(translate('OpenLP.FileSystemLibraryItem',
                                                     'Choose the folder to show in the library.'))
        self.add_folder_action.setText(UiStrings().AddFolder)
        self.add_folder_action.setToolTip(UiStrings().AddFolderDot)
        self.refresh_action.setText(translate('OpenLP.FileSystemLibraryItem', 'Refresh'))
        self.refresh_action.setToolTip(translate('OpenLP.FileSystemLibraryItem', 'Reload the folder from disk.'))

    def add_start_header_bar(self):
        """
        Add the "choose folder" button to the start of the toolbar
        """
        self.choose_root_action = self.toolbar.add_toolbar_action(
            'choose_root_action', icon=UiIcons().open, triggers=self.on_choose_root_click)

    def add_middle_header_bar(self):
        """
        Add the folder buttons after the main buttons
        """
        self.add_folder_action = self.toolbar.add_toolbar_action(
            'add_folder_action', icon=UiIcons().new_group, triggers=self.on_add_folder_click)
        self.refresh_action = self.toolbar.add_toolbar_action(
            'refresh_action', icon=UiIcons().repeat, triggers=self.on_refresh_click)

    def _register_default_settings(self):
        """
        Make sure there are default values for the settings of this library, including the shortcuts of the list view
        actions, so that plugins based on this class do not need to add them to the core settings
        """
        name = 'shortcuts/listView{name}'.format(name=self.plugin.name.title())
        defaults = {
            self.settings_section + '/root folder': None,
            self.settings_section + '/last directory': None,
            name + 'DeleteItem': [QtGui.QKeySequence(QtGui.QKeySequence.StandardKey.Delete)],
            name + 'PreviewItem': [QtGui.QKeySequence(QtCore.Qt.Key.Key_Return),
                                   QtGui.QKeySequence(QtCore.Qt.Key.Key_Enter)],
            name + 'LiveItem': [QtGui.QKeySequence(QtCore.Qt.Key.Key_Shift + QtCore.Qt.Key.Key_Return),
                                QtGui.QKeySequence(QtCore.Qt.Key.Key_Shift + QtCore.Qt.Key.Key_Enter)],
            name + 'ServiceItem': [QtGui.QKeySequence(QtCore.Qt.Key.Key_Plus),
                                   QtGui.QKeySequence(QtCore.Qt.Key.Key_Equal)],
        }
        Settings.extend_default_settings(defaults)

    def add_list_view_to_toolbar(self):
        """
        Creates the tree widget which lists the folder
        """
        self._register_default_settings()
        self.list_view = TreeWidgetWithDnD(self, self.plugin.name)
        self.list_view.setObjectName('{name}TreeView'.format(name=self.plugin.name))
        self.list_view.setIndentation(self.list_view.default_indentation)
        self.list_view.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.allow_internal_dnd = True
        self.page_layout.addWidget(self.list_view)
        self.list_view.setContextMenuPolicy(QtCore.Qt.ContextMenuPolicy.CustomContextMenu)
        if self.has_edit_icon:
            create_widget_action(self.list_view, text=self.plugin.get_string(StringContent.Edit)['title'],
                                 icon=UiIcons().edit, triggers=self.on_edit_click)
            create_widget_action(self.list_view, separator=True)
        if self.can_preview:
            create_widget_action(
                self.list_view,
                'listView{name}{preview}Item'.format(name=self.plugin.name.title(),
                                                     preview=StringContent.Preview.title()),
                text=self.plugin.get_string(StringContent.Preview)['title'],
                icon=UiIcons().preview,
                can_shortcuts=True,
                triggers=self.on_preview_click)
        if self.can_make_live:
            create_widget_action(
                self.list_view,
                'listView{name}{live}Item'.format(name=self.plugin.name.title(), live=StringContent.Live.title()),
                text=self.plugin.get_string(StringContent.Live)['title'],
                icon=UiIcons().live,
                can_shortcuts=True,
                triggers=self.on_live_click)
        if self.can_add_to_service:
            create_widget_action(
                self.list_view,
                'listView{name}{service}Item'.format(name=self.plugin.name.title(),
                                                     service=StringContent.Service.title()),
                can_shortcuts=True,
                text=self.plugin.get_string(StringContent.Service)['title'],
                icon=UiIcons().add,
                triggers=self.on_add_click)
        if self.add_to_service_item:
            create_widget_action(self.list_view, separator=True)
            create_widget_action(
                self.list_view,
                text=translate('OpenLP.MediaManagerItem', '&Add to selected Service Item'),
                icon=UiIcons().add,
                triggers=self.on_add_edit_click)
        create_widget_action(self.list_view, separator=True)
        create_widget_action(self.list_view, text=UiStrings().AddFolder, icon=UiIcons().new_group,
                             triggers=self.on_add_folder_click)
        create_widget_action(self.list_view, text=translate('OpenLP.FileSystemLibraryItem', 'Show in file manager'),
                             icon=UiIcons().open, triggers=self.on_show_in_file_manager_click)
        if self.has_delete_icon:
            create_widget_action(self.list_view, separator=True)
            create_widget_action(
                self.list_view,
                'listView{name}{delete}Item'.format(name=self.plugin.name.title(), delete=StringContent.Delete.title()),
                text=self.plugin.get_string(StringContent.Delete)['title'],
                icon=UiIcons().delete,
                can_shortcuts=True, triggers=self.on_delete_click)
        self.add_custom_context_actions()
        self.menu = QtWidgets.QMenu()
        self.menu.addActions(self.list_view.actions())
        self.list_view.doubleClicked.connect(self.on_double_clicked)
        self.list_view.itemSelectionChanged.connect(self.on_selection_change)
        self.list_view.customContextMenuRequested.connect(self.context_menu)

    def initialise(self):
        """
        Load the folder when the plugin is activated
        """
        self.reload()

    # Hooks for descendant classes

    def is_supported_file(self, file_path: Path) -> bool:
        """
        Return True if the file should be listed in the library

        :param file_path: The file to check
        """
        raise NotImplementedError('is_supported_file needs to be implemented by the descendant class')

    def load_item(self, file_path: Path) -> Optional[QtWidgets.QTreeWidgetItem]:
        """
        Create the QTreeWidgetItem for a file. Override this to set icons, thumbnails etc.

        :param file_path: The file to create the item for
        """
        tree_item = QtWidgets.QTreeWidgetItem([file_path.name])
        tree_item.setToolTip(0, str(file_path))
        return tree_item

    def delete_item(self, file_path: Path):
        """
        Called just before a file is moved to the trash, so that descendant classes can clean up thumbnails etc.
        The file still exists when this is called.

        :param file_path: The file that is being removed
        """
        pass

    def related_files(self, file_path: Path) -> List[Path]:
        """
        Files which belong to a library file, e.g. the audio file of a song. They are not listed, but they are copied,
        moved and deleted together with the file.

        :param file_path: The library file
        """
        return []

    # Loading the folder

    def iter_files(self, folder: Optional[Path] = None) -> Iterator[Path]:
        """
        Walk through a folder (the root folder by default) and yield all the supported files in it

        :param folder: The folder to walk through
        """
        folder = folder or self.root_path
        if not folder:
            return
        for dir_path, dir_names, file_names in os.walk(folder):
            dir_names[:] = [name for name in dir_names if not name.startswith('.')]
            for file_name in file_names:
                file_path = Path(dir_path) / file_name
                if not file_name.startswith('.') and self.is_supported_file(file_path):
                    yield file_path

    def on_directory_changed(self, path: str):
        """
        Something changed on disk, reload the library after things have calmed down

        :param path: The folder that changed
        """
        self._reload_timer.start()

    def on_refresh_click(self):
        """
        Reload the library from disk
        """
        self.reload()

    def _expanded_folders(self) -> set:
        """
        Returns the paths of the folders that are expanded in the tree
        """
        expanded = set()
        iterator = QtWidgets.QTreeWidgetItemIterator(self.list_view)
        while iterator.value():
            tree_item = iterator.value()
            if tree_item.data(0, ItemTypeRole) == ItemType.Folder and tree_item.isExpanded():
                expanded.add(tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole))
            iterator += 1
        return expanded

    def reload(self, select_paths: Optional[List[Path]] = None):
        """
        Reload the whole library from disk, keeping the expanded folders and the selection

        :param select_paths: Paths to select after loading, defaults to the current selection
        """
        expanded = self._expanded_folders()
        if not select_paths:
            select_paths = [item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in self.list_view.selectedItems()]
        # Make sure newly added items are visible
        for path in select_paths:
            if isinstance(path, Path):
                expanded.update(path.parents)
        if self._watcher.directories():
            self._watcher.removePaths(self._watcher.directories())
        self.list_view.blockSignals(True)
        self.list_view.clear()
        self._file_paths = []
        root_path = self.root_path
        if root_path:
            self._watcher.addPath(str(root_path))
            self._load_folder(root_path, self.list_view.invisibleRootItem(), expanded, select_paths)
        else:
            placeholder = QtWidgets.QTreeWidgetItem([translate('OpenLP.FileSystemLibraryItem',
                                                               'No folder chosen. Click "Choose folder" to start.')])
            placeholder.setFlags(QtCore.Qt.ItemFlag.NoItemFlags)
            self.list_view.addTopLevelItem(placeholder)
        self.list_view.blockSignals(False)

    def _load_folder(self, folder: Path, parent_item: QtWidgets.QTreeWidgetItem, expanded: set, select_paths: list):
        """
        Recursively add the contents of a folder to the tree

        :param folder: The folder to load
        :param parent_item: The tree item to add the contents to
        :param expanded: The folders that should be expanded
        :param select_paths: The paths that should be selected
        """
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        sub_folders = sorted((entry for entry in entries if entry.is_dir() and not entry.name.startswith('.')),
                             key=lambda entry: get_natural_key(entry.name))
        files = sorted((entry for entry in entries if entry.is_file() and not entry.name.startswith('.')),
                       key=lambda entry: get_natural_key(entry.name))
        for entry in sub_folders:
            path = Path(entry.path)
            self._watcher.addPath(str(path))
            folder_item = QtWidgets.QTreeWidgetItem([entry.name])
            folder_item.setIcon(0, UiIcons().folder)
            folder_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, path)
            folder_item.setData(0, ItemTypeRole, ItemType.Folder)
            folder_item.setToolTip(0, str(path))
            parent_item.addChild(folder_item)
            self._load_folder(path, folder_item, expanded, select_paths)
            folder_item.setExpanded(path in expanded)
            folder_item.setSelected(path in select_paths)
        for entry in files:
            path = Path(entry.path)
            if not self.is_supported_file(path):
                continue
            tree_item = self.load_item(path)
            if not tree_item:
                continue
            tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, path)
            tree_item.setData(0, ItemTypeRole, ItemType.File)
            parent_item.addChild(tree_item)
            tree_item.setSelected(path in select_paths)
            self._file_paths.append(path)

    def get_file_list(self) -> List[Path]:
        """
        Return all the files in the library
        """
        return list(self._file_paths)

    def selected_file_paths(self) -> List[Path]:
        """
        Return the selected files. Selected folders are expanded to the files directly inside them.
        """
        file_paths = []
        for tree_item in self.list_view.selectedItems():
            if tree_item.data(0, ItemTypeRole) == ItemType.File:
                file_paths.append(tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole))
            elif tree_item.data(0, ItemTypeRole) == ItemType.Folder:
                for index in range(tree_item.childCount()):
                    child = tree_item.child(index)
                    if child.data(0, ItemTypeRole) == ItemType.File:
                        file_paths.append(child.data(0, QtCore.Qt.ItemDataRole.UserRole))
        return file_paths

    def _get_tree_item(self, item) -> Optional[QtWidgets.QTreeWidgetItem]:
        """
        Turn whatever was passed to generate_slide_data into a tree item
        """
        if item is None:
            return self.list_view.currentItem()
        if isinstance(item, QtCore.QModelIndex):
            return self.list_view.itemFromIndex(item)
        return item

    def folder_files(self, folder: Path) -> List[Path]:
        """
        Return the supported files directly inside a folder, in the same order as they are shown in the library

        :param folder: The folder to list
        """
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return []
        return [Path(entry.path) for entry in sorted(entries, key=lambda entry: get_natural_key(entry.name))
                if entry.is_file() and not entry.name.startswith('.') and self.is_supported_file(Path(entry.path))]

    def on_add_click(self):
        """
        Add the selected items to the service. When each file is a service item of its own, selected folders add the
        files directly inside them.
        """
        if self.single_service_item or not self.list_view.selectedIndexes():
            super().on_add_click()
            return
        drop_position = self.service_manager.get_drop_position()
        for file_path in self.selected_file_paths():
            self.add_to_service(self.create_item_from_id(file_path), position=drop_position)
            if drop_position != -1:
                drop_position += 1

    def create_item_from_id(self, item_id: Any) -> QtWidgets.QTreeWidgetItem:
        """
        Create a tree item from a file path, used by the remote API. Paths outside the library folder are not accepted,
        their items have no type and are ignored by :meth:`generate_slide_data`.

        :param item_id: The path of the file
        """
        path = Path(item_id)
        tree_item = QtWidgets.QTreeWidgetItem([path.name])
        tree_item.setData(0, QtCore.Qt.ItemDataRole.UserRole, path)
        root_path = self.root_path
        if root_path and path.resolve().is_relative_to(root_path.resolve()):
            tree_item.setData(0, ItemTypeRole, ItemType.Folder if path.is_dir() else ItemType.File)
        return tree_item

    @QtCore.Slot(str, bool, result=list)
    def search(self, string: str, show_error: bool = True) -> list[list[Any]]:
        """
        Search the file names in the library

        :param string: The text to search for
        :param show_error: Unused
        :return: A list of [file path, file name] pairs
        """
        string = string.lower()
        return [[str(path), path.name] for path in self._file_paths if string in path.name.lower()]

    # Changing the contents of the folder

    def on_choose_root_click(self):
        """
        Let the user pick the folder which is shown in the library
        """
        folder = FileDialog.getExistingDirectory(self, translate('OpenLP.FileSystemLibraryItem', 'Choose folder'),
                                                 self.root_path or Path.home())
        if folder:
            self.root_path = folder

    def _require_root(self) -> Optional[Path]:
        """
        Returns the root folder, showing an error if it has not been chosen
        """
        root_path = self.root_path
        if not root_path:
            critical_error_message_box(
                translate('OpenLP.FileSystemLibraryItem', 'No folder chosen'),
                translate('OpenLP.FileSystemLibraryItem', 'You need to choose a folder for the library first.'))
        return root_path

    def on_add_folder_click(self):
        """
        Create a new folder on disk inside the current folder
        """
        if not self._require_root():
            return
        parent_folder = self.current_folder
        name, ok = QtWidgets.QInputDialog.getText(self, UiStrings().AddFolder,
                                                  translate('OpenLP.FileSystemLibraryItem', 'Folder name:'))
        name = name.strip()
        if not ok or not name:
            return
        new_folder = parent_folder / name
        try:
            new_folder.mkdir()
        except OSError as error:
            critical_error_message_box(message=translate('OpenLP.FileSystemLibraryItem',
                                                         'Could not add the new folder: {error}').format(error=error))
            return
        self.reload(select_paths=[new_folder])

    def on_show_in_file_manager_click(self):
        """
        Open the current folder in the file manager of the operating system
        """
        folder = self.current_folder
        if folder:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(folder)))

    def handle_mime_data(self, data: dict):
        """
        Files or folders were dropped from the desktop. Folders are copied as they are, files are filtered.

        :param data: A dictionary containing the list of files to be loaded and the target
        """
        file_paths = [path for path in data['file_paths'] if path.is_dir() or self.is_supported_file(path)]
        if len(file_paths) < len(data['file_paths']):
            critical_error_message_box(
                translate('OpenLP.MediaManagerItem', 'Invalid File Type'),
                translate('OpenLP.FileSystemLibraryItem', 'Some of the files are not supported and were ignored.'))
        if file_paths:
            self.validate_and_load(file_paths, data.get('target'))

    def _target_folder(self, target_item: Optional[QtWidgets.QTreeWidgetItem]) -> Optional[Path]:
        """
        Work out which folder files should be put into

        :param target_item: The tree item that was dropped on, if any
        """
        if target_item is None:
            return self.current_folder
        path = target_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if not isinstance(path, Path):
            return self.root_path
        return path if target_item.data(0, ItemTypeRole) == ItemType.Folder else path.parent

    def validate_and_load(self, file_paths: List[Path], target_folder: Optional[QtWidgets.QTreeWidgetItem] = None):
        """
        Copy files from the file dialog or from drag and drop into the library folder.
        Files which already are inside the library folder are left where they are.

        :param file_paths: The files to add
        :param target_folder: The tree item that the files were dropped on
        """
        self.application.set_normal_cursor()
        root_path = self._require_root()
        if not root_path:
            return
        destination = self._target_folder(target_folder)
        added = []
        skipped = []
        for file_path in file_paths:
            file_path = Path(file_path)
            if file_path.resolve().is_relative_to(root_path.resolve()):
                added.append(file_path)
                continue
            target_path = destination / file_path.name
            if target_path.exists():
                skipped.append(file_path.name)
                continue
            try:
                if file_path.is_dir():
                    shutil.copytree(file_path, target_path)
                else:
                    shutil.copy2(file_path, target_path)
                added.append(target_path)
            except OSError as error:
                skipped.append('{name} ({error})'.format(name=file_path.name, error=error))
                continue
            if not file_path.is_dir():
                skipped += self._transfer_related_files(file_path, destination, shutil.copy2)
        if file_paths:
            self.settings.setValue(self.settings_section + '/last directory', Path(file_paths[0]).parent)
        self.reload(select_paths=added)
        if skipped:
            critical_error_message_box(translate('OpenLP.FolderLibraryItem', 'File Exists'),
                                       translate('OpenLP.FileSystemLibraryItem',
                                                 'The following files were not added:\n{names}'
                                                 ).format(names='\n'.join(skipped)))

    def dnd_move_internal(self, target: Optional[QtWidgets.QTreeWidgetItem]):
        """
        Move files and folders around inside the library folder

        :param target: The tree item the items were dropped on
        """
        destination = self._target_folder(target) if target is not None else self.root_path
        if not destination:
            return
        moved = []
        for tree_item in self.list_view.selectedItems():
            path = tree_item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if not isinstance(path, Path) or path.parent == destination or destination.is_relative_to(path):
                continue
            target_path = destination / path.name
            if target_path.exists():
                critical_error_message_box(translate('OpenLP.FolderLibraryItem', 'File Exists'),
                                           translate('OpenLP.FileSystemLibraryItem',
                                                     '"{name}" already exists in the target folder.'
                                                     ).format(name=path.name))
                continue
            related = [] if path.is_dir() else self.related_files(path)
            try:
                shutil.move(str(path), str(target_path))
                moved.append(target_path)
            except OSError as error:
                critical_error_message_box(message=str(error))
                continue
            skipped = self._transfer_related_files(path, destination, shutil.move, related)
            if skipped:
                critical_error_message_box(message=translate('OpenLP.FileSystemLibraryItem',
                                                             'The following files were not moved:\n{names}'
                                                             ).format(names='\n'.join(skipped)))
        self.reload(select_paths=moved)

    def _transfer_related_files(self, file_path: Path, destination: Path, transfer,
                                related: Optional[List[Path]] = None) -> List[str]:
        """
        Copy or move the related files of a file into a folder. Nothing is overwritten.

        :param file_path: The library file
        :param destination: The folder to put the files into
        :param transfer: :func:`shutil.copy2` or :func:`shutil.move`
        :param related: The related files, if they were looked up before the library file was moved
        :return: The names of the files which could not be copied or moved
        """
        skipped = []
        for related_path in (self.related_files(file_path) if related is None else related):
            target_path = destination / related_path.name
            if target_path.exists():
                skipped.append(related_path.name)
                continue
            try:
                transfer(str(related_path), str(target_path))
            except OSError as error:
                skipped.append('{name} ({error})'.format(name=related_path.name, error=error))
        return skipped

    def on_delete_click(self):
        """
        Move the selected files and folders to the trash
        """
        if not check_item_selected(
                self.list_view, translate('OpenLP.FolderLibraryItem', 'You must select an item or folder to delete.')):
            return
        paths = [item.data(0, QtCore.Qt.ItemDataRole.UserRole) for item in self.list_view.selectedItems()]
        paths = [path for path in paths if isinstance(path, Path)]
        if not paths:
            return
        if QtWidgets.QMessageBox.question(
                self, translate('OpenLP.FileSystemLibraryItem', 'Delete'),
                translate('OpenLP.FileSystemLibraryItem',
                          'Are you sure you want to move the following to the trash?\n{names}'
                          ).format(names='\n'.join(path.name for path in paths))
        ) != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        failed = []
        for path in paths:
            related = [] if path.is_dir() else self.related_files(path)
            for file_path in (self.iter_files(path) if path.is_dir() else [path]):
                self.delete_item(file_path)
            if not move_to_trash(path):
                failed.append(path.name)
                continue
            failed += [related_path.name for related_path in related if not move_to_trash(related_path)]
        self.reload()
        if failed:
            critical_error_message_box(message=translate('OpenLP.FileSystemLibraryItem',
                                                         'Could not delete the following:\n{names}'
                                                         ).format(names='\n'.join(failed)))
