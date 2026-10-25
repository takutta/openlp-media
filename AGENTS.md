# AGENTS.md

## Project

Four OpenLP plugins (Media Folder, Image Folder, Presentation Folder and Song Folder) that use file paths directly
instead of a database: the folder chosen on disk *is* the library. The plugins were first made in a fork of OpenLP
in the same GitHub repository (`takutta/openlp-media`). This code is on the `main` branch, which has no history in
common with the fork. The history of the fork is on the `feature/filesystem-plugins` branch.

- OpenLP is the git submodule `upstream/` (`https://gitlab.com/openlp/openlp.git`, OpenLP is not on GitHub).
  It is pinned to the release the plugins are tested against (now `3.1.7`, the latest release). OpenLP itself is
  not changed, and it is not released from this repository.
- The plugins run on both OpenLP 3.1 (PyQt5, Python 3.11 in the official build) and the coming OpenLP 4 (PySide6,
  upstream `master`). They are tested against both.
- Users install the plugins into OpenLP's community plugin folder (below), with the exe installer or from the zip.
- The code of the original plugins (`media`, `images`, `presentations`, `songs`) is reused by importing it, but it
  is not changed.

## Layout

```
plugins/                 the plugins as they are installed
  filesystem_library/    shared code (not a plugin), compat.py
  media_folder/  image_folder/  presentation_folder/  song_folder/
plugin_tests/            pytest tests, one folder per plugin
conftest.py              attaches the plugins to OpenLP for the tests (below)
tools/build.py           translations, zip and exe into dist/
tools/installer.iss      Inno Setup installer
tools/INSTALL.txt        English install guide, in the zip and at the end of the installer
tools/ASENNUSOHJE.txt    the same in Finnish; keep the two guides in step
tools/smoke.py           smoke test that starts OpenLP
tools/migrate_database.py  old OpenLP libraries into folders (one-off, below)
upstream/                OpenLP (submodule)
VERSION                  version of the plugins
```

## Installing and loading in OpenLP

- OpenLP loads community plugins from `<DataDir>/contrib/plugins/<name>/*plugin.py` with the module name
  `contrib.plugins.<name>.<file>` (`pluginmanager.py`, `extension_loader(..., community=True)`).
  `DataDir` is `AppLocation.get_directory(DataDir)`: `%APPDATA%\openlp\data` on Windows, `~/.local/share/openlp`
  on Linux, `~/Library/Application Support/openlp/Data` on macOS. The folder is the same in portable mode and when
  the user has changed the data folder, because the core does not use `get_data_path()` for it.
- Imports between the plugins are therefore relative (`from ...filesystem_library.libraryitem import ...`).
  The same files work both as `contrib.plugins.*` (installed) and as `openlp.plugins.*` (in the tests).
  OpenLP's own modules are imported absolutely (`openlp.core...`, `openlp.plugins.songs...`).
- The official Windows build (PyInstaller) has OpenLP's plugins as `.py` source in `App/OpenLP/plugins`, so the
  modules of the original plugins can be imported in the frozen build too.
- The new plugins are inactive by default (`<plugin>/status` = `PluginStatus.Inactive`). The user enables them in
  Settings > Manage Plugins.

## OpenLP 3.1 and 4: `plugins/filesystem_library/compat.py`

All the differences are in this file. Qt is always imported from there, never directly from PyQt5 or PySide6.

- The Qt binding is the one the core uses (`'PySide6' in sys.modules` after `openlp.core.common.settings` has been
  imported). `Signal`/`Slot` are `pyqtSignal`/`pyqtSlot` in PyQt5.
- `get_supported_media_suffix()` only exists in OpenLP 4 (Qt Multimedia). 3.1 uses the `AUDIO_EXT` and `VIDEO_EXT`
  lists. `get_file_type_glob()` only exists in 4, 3.1 uses `*.suffix`.
- Enums are written fully qualified (`QtCore.Qt.ItemDataRole.UserRole`), which works in both. `exec()` works in
  both.
- Other differences are handled in the plugin code:
  - The parameters of `extension_loader()` changed after 3.1.7, so Presentation Folder imports the presentation
    controllers itself with `importlib`.
  - `find_controller_by_type` in 3.1 is case-sensitive about the file suffix. Presentation Folder lowercases the
    suffix before the call.
  - The preview of the next line of a song (`{preview}`) only exists in OpenLP 4. It is only used if the setting
    `songs/preview_enabled` is in the core's default settings.
- PowerPoint: the original Presentations plugin checks its controllers (`check_available`) even when it is
  inactive. If PowerPoint is checked again right after it has been closed, `Dispatch('PowerPoint.Application')`
  hangs and OpenLP does not start. The `check_available` of Presentation Folder's controllers is therefore the
  `is_available` of the original plugin's matching controller (`register_controller`), so PowerPoint is only
  checked once.

## What has been done

### Shared code: `plugins/filesystem_library/`

This folder is not a plugin (it has no `*plugin.py` file, so the plugin manager does not load it), but the shared
library of the plugins.

- `libraryitem.py`: the base class `FileSystemLibraryItem` (below).
- `compat.py`: the differences between OpenLP 3.1 and 4 (above).
- `translations.py`: `install_translator(path)` installs the `.qm` translation of the current language from a
  folder with its own `QTranslator`. Call it at the start of the plugin's constructor, before `super().__init__()`,
  for both `LIBRARY_TRANSLATIONS_PATH` and the plugin's own `i18n` folder.
- `i18n/fi.ts`: Finnish translation of the base class.

#### `FileSystemLibraryItem`

`FileSystemLibraryItem(MediaManagerItem)` shows the root folder as a tree (folders first, natural order, hidden
files skipped).

- The root folder is the setting `<plugin>/root folder`, chosen with "Choose folder" in the toolbar.
  In a portable OpenLP, a folder inside the portable folder is saved as a relative path.
- A `QFileSystemWatcher` with a 500 ms debounce reloads the tree when something changes on disk.
  Expanded folders and the selection are kept.
- Adding files (dialog or drag and drop) copies them into the selected folder. Nothing is overwritten.
- Dragging inside the library moves files on disk. "Add folder" makes a real folder.
- Deleting asks for confirmation and moves the files to the recycle bin (`QFile.moveToTrash`). `delete_item()` is
  called for each file just before it is moved, so the file still exists (the thumbnail folder of a presentation is
  named by the hash of the file's contents).
- Tree items: `UserRole` = `Path`, `ItemTypeRole` (`UserRole + 1`) = `'folder'` / `'file'`.
- A subclass implements `is_supported_file()` and `generate_slide_data()`. It can also override `load_item()` and
  `delete_item()`.
- `related_files(file)` (empty by default) returns the files that belong to a file but are not shown in the tree
  (for example a song's audio file). They are copied, moved and moved to the recycle bin together with the file.
  Nothing is overwritten: if the target already has a file with the same name, it is left in place and the user is
  told.
- `folder_files(folder)` returns the supported files directly in a folder, in the same order as in the tree.
- `on_add_click()`: if `single_service_item` is False, a selected folder adds each of its files to the service
  separately.
- `create_item_from_id()` (remote API) only gives a type to paths inside the root folder, so the remote cannot show
  other files on the disk.
- The remote API looks up the signals `<plugin name>_go_live` and `<plugin name>_add_to_service`. A subclass must
  define them with exactly these names (for example `image_folder_go_live`), otherwise remote commands crash.
- If a subclass sets `has_edit_icon`, the context menu gets "Edit" (`on_edit_click`).
- `_get_tree_item(item)` turns the value passed to `generate_slide_data()` (None / `QModelIndex` / item) into a
  tree item.
- The class registers its own default settings (`root folder`, `last directory` and the list view shortcuts
  `shortcuts/listView<Name>…`). Otherwise `create_widget_action` fails with a KeyError.

### Media Folder plugin: `plugins/media_folder/`

- The plugin registers its own default setting `media_folder/status` (`Settings.extend_default_settings`).
- The core only knows the service item icons of its own plugins, so `generate_slide_data()` sets the icon itself.
  The service item also has `OnLoadUpdate`, so that `service_load()` restores the icon when a service is opened
  from a file.
- The remote API's media play/pause/stop (`/api/v2/media/*`) does not work for media_folder items, because the core
  checks the plugin name (`name != 'media'`). There is no workaround. Changing slides and the rest of the remote
  control work. Upstream could be asked to change the check to `service_item.is_media()`.
- The plugin name is `media_folder`. It must match `de_hump(MediaFolderPlugin)`, because `State` looks up the
  plugin as `<name>_plugin`.
- Lists audio and video files by `get_supported_media_suffix()`, whatever the case of the suffix.
- Adding a folder to the service adds each of its media files separately.
- Network and device streams were left out, because they have no file path.

### Image Folder plugin: `plugins/image_folder/`

- Its own default settings: `image_folder/status`, `image_folder/background mode`, `image_folder/theme`.
- `ImageFolderTab` is the `ImageTab` of the `images` plugin, reading and writing the `image_folder/*` settings.
- Thumbnails are in `<data>/image_folder/thumbnails`. The core looks for the plugin's thumbnails there when a
  service is opened from a file. There is no database, so a thumbnail is named by the sha256 of the image's *path*
  (not its contents).
- The selected images and folders (the images directly in a folder) become a single image item that can loop.
  With several selected, the title is the plugin's plural name.
- Background replace/reset as in the `images` plugin. The icon is set by the plugin and restored with
  `OnLoadUpdate` + `service_load()`, as in `media_folder`.

### Presentation Folder plugin: `plugins/presentation_folder/`

- Uses the `presentations` plugin's controllers (`*controller.py`), the `PresentationTab` settings page and the
  `MessageListener` class. The controllers are imported from the original plugin's folder with `importlib` (see
  the compat section).
- The controller settings (`presentations/Impress`, `presentations/override app` and so on) are shared with the
  original plugin. Their defaults are already in the core.
- The controllers' `thumbnail_folder` and `temp_folder` are changed to `<data>/presentation_folder/`, because the
  core copies the thumbnails of a service file to `<data>/<plugin name>/thumbnails`.
- The slide controller sends messages as `<service item name>_start` and so on. `FolderMessageListener` registers
  them as `presentation_folder_*` (the original listens to `presentations_*`).
- The core only fixes the thumbnail paths of a service opened from a file for the name `presentations`
  (`serviceitem.py`). `service_load()` does the same: the relative paths of the service file are turned into
  absolute paths in the data folder.
- PDF (and the other `PDF_CONTROLLER_FILETYPES`) are shown as images in Live and Preview, as in the original plugin
  (`service_item.name = 'images'`). In the service it is a command item.
- `populate_display_types` and `clean_up_thumbnails` are borrowed directly from `PresentationMediaItem`, because
  they do not use the database.
- Loading the library does not open any presentations, because starting LibreOffice or PowerPoint for a whole
  folder would be far too slow. A thumbnail appears once the presentation has been previewed, shown or added to the
  service. Icons are cached by the file's modification time.
- The original and the new presentation plugins must not be active at the same time: each starts its own
  controller processes.

### Song Folder plugin: `plugins/song_folder/`

Songs are OpenLyrics files (`*.xml`, any case) in a folder. The files are always the truth, there is no database.

- `lib/songfile.py`: a parser without a database. `parse_song_file()` / `parse_song_xml()` return a `FileSong`
  (titles, authors with types, copyright, CCLI, comments, songbooks, topics, verse order, verses).
  An invalid file raises `SongFileError`.
  - The line handling (chords, formatting tags, `<br/>`) uses the helper methods of the songs plugin's `OpenLyrics`
    class (`_process_lines_mixed_content`, `_process_formatting_tags`), so the result is the same as in the songs
    plugin. `OpenLyrics(None)` is created lazily, because its constructor reads the settings.
  - Two differences from the songs plugin: the indentation and line breaks of the XML are removed (in OpenLyrics a
    line break is only `<br/>`), and text after a page break `<p style="page-break-after…"/>` is kept (the songs
    plugin loses it).
  - Unknown formatting tags are added as temporary (`temporary=True`), the settings are not changed.
  - The parser loads no external entities and nothing from the network (`resolve_entities=False`,
    `no_network=True`).
  - `ordered_verses()`: an entry of the verse order matches the whole name (`v1a`), the tag and number (`v1`, all
    parts) or just the tag (`c`). Without a verse order, the verses are shown in file order.
- `lib/songindex.py`: `SongIndex` is a search index in memory. A file is parsed again only when its `st_mtime_ns`
  or size changes. `update(paths)` syncs the index with the files of the tree (called after each `reload()`).
  `search(text)` requires every word in any field or the file name (normalised: lower case, no punctuation, chords
  or formatting tags).
  - Cache: `load()`/`save()` read and write the index as JSON in `<data>/song_folder/index.json` (the media
    item's `initialise()` loads it, `reload()` saves it if `changed`). A broken cache or one of an old version
    (`CACHE_VERSION`) is ignored. Increase `CACHE_VERSION` when `FileSong` or the search text changes.
  - The index is only used for the names in the tree and for searching. `generate_slide_data()` always parses the
    file again, so that the slides are up to date and the song's own formatting tags are registered (a song read
    from the cache does not register them).
- `lib/mediaitem.py`: `SongFolderMediaItem(FileSystemLibraryItem)`.
  - The tree shows the song's title, and the tooltip has the alternative title, authors and path. A file that
    cannot be read is shown with its file name and an error icon, with the error in the tooltip.
  - A search box above the list filters the tree while typing. Folders without matches are hidden and folders with
    matches are expanded. The filter is kept when the tree reloads.
  - `generate_slide_data()`: verses in verse order, a forced page break (`[--}{--]`) splits slides and an optional
    split (`[---]`) works with `CanSoftBreak`. The footer is made with the songs plugin's `songs/footer template`
    (looks the same as in the songs plugin). `audit` is set, so the songusage plugin logs the use.
    `data_string['file path']` tells the source file.
  - The remote API search (`search()`) uses the index and returns the file path as the id.
  - The songs plugin's settings (`songs/*`) are shared: upper case (`{uc}`), the first slide (songbooks `O1` or
    footer `O2`) and the preview of the next line (`{preview}`, per verse type `PREVIEW_SETTINGS`, OpenLP 4 only)
    work as in the songs plugin. The plugin uses the songs plugin's `SongsTab` as its settings page. If both
    plugins are active, the same settings page appears twice. The page also has settings that do not affect Song
    Folder (SongSelect, "update service on edit", "add song from service").
  - Background audio: an audio file with the same name next to the song (`Song.mp3` for `Song.xml`, audio
    suffixes of `get_supported_media_suffix()`). Needs the State name `media`. `songs/auto play audio` works in the
    core. If there are several audio files with the same name, the first one is played. The audio files are the
    song's `related_files()`, so they are copied, moved and deleted together with the song.
  - On the form's "Background audio" tab you can choose an audio file or remove it. On saving
    (`save_background_audio()`) the chosen file is copied next to the song with the song's name, and the song's
    other audio files are moved to the recycle bin. If the background audio was not changed, nothing is done. A new
    song does not touch audio files that already have its name, unless audio was chosen. If the change fails, the
    song is still saved and the user is told.
  - Theme: OpenLyrics has no theme, so it is kept in the file in its own namespace
    `<openlp:theme xmlns:openlp="http://openlp.org/ns/song-folder">Name</openlp:theme>` (`songfile.THEME_TAG`).
    Other programs ignore it. An empty theme = default.
- The plugin registers the default setting `song_folder/status` and the songs plugin's `song_footer` default, so
  the footer works even when the songs plugin is inactive.
- `lib/songwriter.py`: `song_to_xml(song, original)` and `write_song_file(song, path, keep_contents)` write
  OpenLyrics 0.9 without a database. The file was merged from the work of two parallel sessions.
  - In an existing file, only the edited properties (`EDITED_PROPERTIES`: titles, authors, copyright, CCLI, verse
    order, songbooks, topics, comments) and `<lyrics>` are replaced. They are replaced in place, and new ones are
    added in schema order (`PROPERTY_ORDER`). Everything else is kept in order: tempo, key, publisher, the
    attributes of `<song>` (`createdIn`, `chordNotation`…), foreign elements and the file's own formatting tags
    (also unused ones). New tags used by the lyrics are added. The verses' `<comment>` elements and their own
    attributes (except `lang`) are not kept, because `<lyrics>` is rewritten.
  - A file without the OpenLyrics namespace is moved into the namespace. A broken file or one that is not a song is
    written from scratch.
  - The lyrics are converted (chords, formatting tags, `[---]`, `[--}{--]`) with the songs plugin's `OpenLyrics`
    helper methods, so the result is the same as the songs plugin's export. A `[---]` at the end of a verse is left
    out.
  - The file is indented, but the content of `<lines>` elements is not, because other programs read its spaces as
    text.
  - The file is written to a hidden temporary file in the same folder and swapped in with `os.replace`, so a failed
    save does not break the old file. Errors raise `SongFileError`. The old file's permissions are kept, and a new
    file gets the normal permissions (umask).
  - `song_file_name(title, folder)` makes a file name for a new song from its title (forbidden characters → `_`)
    and adds ` (2)`, ` (3)`… when needed. Nothing is overwritten.
  - The test `test_resource_files_survive_a_round_trip` checks that the songs plugin's OpenLyrics test files stay
    the same when they are written again.
- `forms/editsongform.py`: `SongFileEditForm` is a separate, lighter form (the original is tied to the database).
  - The lyrics are edited as one text, with a line `---[Verse:1]---` at the start of each verse. The format is the
    same as the songs plugin's "Edit All" view. The forms `---[Chorus:1:en]---` (language) and `---[Verse:1a]---`
    (part) work too. The verse type can be written in Finnish, in English or as an abbreviation. Text before the
    first marker is verse 1. Verses with the same name are merged, as when reading.
  - The verse order is shown with translated tags (`S1 K1` in Finnish) and read in both translated and English
    tags.
  - Authors are in a list with their types. Topics and songbooks (`Book #12`) are written one per line.
  - The theme is chosen from the theme list (`theme_manager.get_theme_names()`, updated on the `theme_update_list`
    event). Transposing up/down (`transpose_lyrics`) is shown when `songs/enable chords` is on.
  - The texts use the songs plugin's contexts (`SongsPlugin.EditSongForm` and so on), so most of the Finnish
    translation comes from the core.
- Editing in the media item:
  - "New" writes the song into the selected folder and "Edit" (also in the context menu) into the selected file.
    The file name does not change even if the title changes. The edited song is also always updated in the service
    (`replace_service_item`), unlike in the songs plugin, where it depends on the `songs/update service on edit`
    setting.
  - The service item has `CanEdit`, and `edit_id` is the file path. With these, "Edit" in the service and in the
    preview works (`on_remote_edit`, only for files inside the library). `edit_id` is not saved in the service
    file, so `service_load()` restores it from `data_string['file path']` if the file still exists. Otherwise
    `CanEdit` is removed.
  - If the file changes on disk during editing, the user is asked before it is overwritten. If saving fails, the
    form opens again with its contents. After saving, the file's old entry is removed from the index, because the
    size and timestamp may be the same.
- Still missing:
  - Editing a verse in a separate dialog (the songs plugin's `EditVerseForm`). The form's single text box covers the
    same, so this may not be needed.
  - The remote API's transposing (`/api/v2/plugins/songs/transpose-live-item`) does not work, because the core
    checks the name (`name != 'songs'`). Same as media_folder's play/pause calls.

### The original plugins must stay installed

The new plugins don't need the original ones to be active, but they must be installed (they always come with
OpenLP): `presentation_folder`, `image_folder` and `song_folder` import code from them. Also, the core's
`ServiceItem.validate_item()` and the slide controller check the State name `media`, which the original media
plugin registers even when it is inactive. Without it, `media_folder` items are marked invalid in the service.

### Finnish translations: `plugins/*/i18n/fi.ts`

- `filesystem_library/i18n/fi.ts`: the context `OpenLP.FileSystemLibraryItem` and the core texts the base class
  uses (`OpenLP.Ui` "Add folder" and so on), some of which are missing from the core's Finnish translation.
- `media_folder/i18n/fi.ts`: the contexts `MediaFolderPlugin`, `MediaFolderPlugin.MediaItem` and the
  `MediaPlugin.MediaItem` texts used.
- `song_folder/i18n/fi.ts`: the contexts `SongFolderPlugin`, `SongFolderPlugin.MediaItem` and the footer's
  `OpenLP.Ui` and `SongsPlugin.MediaItem` texts. The names of the author types (`SongsPlugin.AuthorType`) come from
  the core's translation. The `SongsPlugin.EditSongForm` texts of the form were copied from the core's translation.
  `SongsPlugin.EditVerseForm` ("Pakotettu jako") was added by hand, because it is missing from the core and lupdate
  does not find `UiStrings` texts. lupdate marks messages added by hand as obsolete (`vanished`), so check them
  after an update.
- `image_folder/i18n/fi.ts`: `ImageFolderPlugin`, the `ImagePlugin.MediaItem` texts used and `ImagesPlugin.ImageTab`
  added by hand, which is missing from the core's translation.
- `presentation_folder/i18n/fi.ts`: `PresentationFolderPlugin` and the `PresentationPlugin.MediaItem` texts used.
  The texts of the `PresentationTab` settings page come from the core's translation.
- The terms follow OpenLP's Finnish translation: service = "Lista", live = "Esitys", presentation = "Presentaatio"
  (not "esitys", which means live), Manage Plugins = "Moduulien hallinta", Active = "Käytössä". Use the same words
  in the install guide.
- Updating after the source has changed (example): `uvx --from pyside6-essentials pyside6-lupdate
  plugins/media_folder/*.py plugins/media_folder/lib/*.py -ts plugins/media_folder/i18n/fi.ts`. For song_folder,
  include `plugins/song_folder/forms/*.py` too.
- `.qm` files are not committed. `tools/build.py` compiles them next to the `.ts` files (`--translations-only` only
  compiles). lrelease comes from PySide6 (with uvx if it is not installed); the `.qm` format is the same in Qt 5
  and 6.

## Development

```
git submodule update --init
uv venv --python 3.11 && uv pip install -r requirements.txt     # OpenLP 3.1 (PyQt5)
QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m pytest          # .venv/bin/python on Linux
.venv/Scripts/python -m flake8 --max-line-length 120 plugins plugin_tests tools conftest.py
```

- `conftest.py` adds the `upstream/` folder to `sys.path`, adds the `plugins/` folder to the `__path__` of the
  `openlp.plugins` package (the tests import for example `openlp.plugins.song_folder.lib.mediaitem` and patch with
  the same names) and loads OpenLP's fixtures (`pytest_plugins = ['tests.conftest']`). Test resources come from
  `tests.utils.constants.RESOURCE_PATH`, that is `upstream/tests/resources`. The test folder is therefore
  `plugin_tests`, not `tests`, which is OpenLP's package.
- `requirements.txt` has OpenLP 3.1's dependencies for running it from source. PyMuPDF 2 crashes with PyQt5 on
  Windows (access violation on import), so it is limited to `< 1.25`.
- OpenLP 4 (PySide6): `git -C upstream checkout origin/master`, then `uv sync --all-extras` in `upstream` and the
  tests with the Python of `upstream/.venv`. OpenLP 4 reads its version from git with hatchling, so it only works
  installed (`uv sync`), not from plain source. `uv sync` changes upstream's `uv.lock`; restore it
  (`git -C upstream checkout uv.lock`) and finally put the submodule back on the tag (`git -C upstream checkout
  3.1.7`).
- Smoke test with the real application: starts OpenLP in portable mode, installs the plugins into the work
  folder's `appdata/.../contrib/plugins` (sets the `APPDATA` and `XDG_DATA_HOME` variables), adds images, a PDF and
  a song to the service, edits the song with the real form, saves and opens the service and tries the remote search
  and live. Prints `SMOKE RESULT`:
  ```
  QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \\
      .venv/Scripts/python tools/smoke.py <empty work folder>
  ```
  The Finnish texts are only checked if the `.qm` files have been compiled. A prepared ini file must contain
  `settings/version`, `core/has run wizard` and today's `core/last version test` and `api/last version test`.
  Otherwise the application stays in a modal dialog (first run, or the notice about a new web remote).
- Trying the official build on Windows: download the portable build (`https://get.openlp.org/3.1.7/`), extract it
  with 7-Zip and run `App/OpenLP/OpenLP.exe -p -P <folder> -l debug`. The log goes to `<folder>/Other`. When
  `APPDATA` points to a test folder, the real profile is not touched. `QT_QPA_PLATFORM=offscreen` does not stop all
  windows in the frozen build. If the computer has PowerPoint, wait between test runs until `POWERPNT.EXE` has
  closed. A heavy load (for example a game) can hang the PowerPoint check.
- In a clean Linux container the dependencies need the packages `pkg-config libicu-dev libpq-dev` and for
  Qt/WebEngine `libegl1 libgl1 libxkbcommon0 libnss3 libxcomposite1 libxdamage1 libxrandr2 libxtst6 libasound2t64
  libfontconfig1 libdbus-1-3 libxkbfile1`.
- Reading a song can add temporary tags to the global `FormattingTags.html_expands` list. `conftest.py` restores
  the list after each test.
- When tests create real widgets, `ActionList.shortcut_map` must be cleared between tests.
- Use the same GPL license header in files as elsewhere in the code.

## Migration tool: `tools/migrate_database.py`

A one-off tool that turns the database libraries of an old portable OpenLP into folders for the new plugins.
It was first made in the fork for one user's data (`E:\openlp` → `E:\openlp-muunnettu`). It has no tests: the
result is checked by reading the plan.

- `plan <source> <target>` matches the rows of the image, media and presentation databases to the source's files
  by sha256 (the databases keep the hash), inside `.osz` service files (embedded files are named by their hash) or
  by name and the end of the folder path. Writes `plan.csv`, `missing.csv` and `summary.txt`. The hashes are cached
  in `hash-cache.json`, so running it again is fast.
- `copy <source> <target>` only does what the plan says (the actions copy/extract/song), skips files already
  copied and makes the `Data` folder: everything except the folders of the old libraries and `Temp`. In
  `OpenLP.ini`, the new plugins' `root folder` is relative and `status` is a number (as OpenLP itself saves it).
  `Settings()` without a file name is the registry on Windows, so the ini is opened by name.
- The songs are exported with the songs plugin's `OpenLyrics.song_to_xml` from a copy of the database, which is
  upgraded first (`upgrade_db`). Of the `.xml` files on disk, only OpenLyrics songs that are not in the database are
  included.
- Duplicate = same contents. The shortest path wins (folder levels, characters, alphabetical). Also left out are
  other file types, `*_files`/`*_tiedostot` folders and files in the same folder as an `.exe`/`.msi`.
- `--fi` switches the names of the folders, files, CSV columns and actions to Finnish (`WORDS`). The same option
  must be given to both steps.
- Run in the development environment: the script adds `upstream/` to the path and the plugins to the
  `openlp.plugins` package like `conftest.py`. Qt comes from `compat.py`.

## Release

1. Update `VERSION`.
2. `.venv/Scripts/python tools/build.py` makes in `dist/` the files
   `openlp-folder-plugins-<version>.zip` (plugins, `INSTALL.txt`, `ASENNUSOHJE.txt`, `LICENSE.txt`,
   `tools/migrate_database.py`) and
   `openlp-folder-plugins-<version>-setup.exe`, if Inno Setup is installed (`scoop install extras/inno-setup`).
3. The installer installs without administrator rights into `{userappdata}\openlp\data\contrib\plugins`.
   It first removes the folders of the old version and refuses to install if OpenLP is running (a WMI query, not
   `tasklist | find`, because Git Bash's `find` comes first in PATH). The uninstaller is in
   `contrib\folder-plugins-uninstall`, because OpenLP looks for plugins in the `plugins` folder. The installer asks
   for the language first (English or Finnish, the Windows language preselected). The language-dependent texts are
   in the `[CustomMessages]` section and the guide at the end is the `InfoAfterFile` value of the `[Languages]`
   lines. In a silent test, choose the language with `/LANG=en` or `/LANG=fi`.
4. Silent test: `setup.exe /VERYSILENT /SUPPRESSMSGBOXES` and
   `contrib\folder-plugins-uninstall\unins000.exe /VERYSILENT`. It installs into the real profile, so remove the
   installation after the test.
5. The installer is not signed, so Windows SmartScreen warns about it (the guide explains what to do).

## Known limitations

- `test_index_cache` failed twice under heavy load on Windows (a song was read into the index again even though the
  cache was fresh). It did not happen again in 15 runs in a row. The only effect in use is an extra file read.
- The remote API's media play/pause/stop and song transposing do not work for the folder plugins' items, because
  the core checks the plugin name (`name != 'media'`, `name != 'songs'`). Upstream could be asked for a check like
  `service_item.is_media()`.
- LibreOffice and PowerPoint have only been tested with mock controllers and by starting OpenLP (not by showing a
  presentation).

## Next

1. Try all the plugins in a real GUI, presentations also with LibreOffice and PowerPoint.
2. Possibly GitHub Actions that run the tests against 3.1.7 and master and make the release files.
3. Custom slides (`custom`) if needed, for example as text files in a folder.
