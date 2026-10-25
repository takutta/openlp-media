# OpenLP Folder Plugins

**Your folders are the library.** Four plugins for [OpenLP](https://openlp.org) that show a folder on disk
directly, with no database in between.

| Plugin | Shows | Instead of |
| --- | --- | --- |
| Media Folder | Audio and video files | Media |
| Image Folder | Images | Images |
| Presentation Folder | PDF, LibreOffice and PowerPoint files | Presentations |
| Song Folder | [OpenLyrics](https://docs.openlyrics.org) song files (`*.xml`) | Songs |

They run on OpenLP 3.1.7 and later, including the coming OpenLP 4. OpenLP itself is not changed: the plugins are
installed next to it as community plugins, and the original plugins stay as they are.

## The problem

OpenLP's built-in plugins keep their own database of your files. For images, media and presentations, that
database stores a list of file paths. For songs, it stores the songs themselves. That causes several problems:

- **Two sources of truth.** A file exists on disk, and a separate record of it exists in the database. Rename,
  move or delete the file in your file manager and OpenLP still lists the old path. Add a file to the folder
  and OpenLP doesn't see it until you import it by hand.
- **Portable use breaks.** The database stores absolute paths such as `D:\Church\Media\intro.mp4`. Copy OpenLP
  to a USB stick or another computer and the drive letter or user folder changes, and every item points to
  nowhere.
- **Your songs are locked in.** Songs live in an SQLite file. You can't edit one in a text editor, compare
  versions, sync them with a cloud folder or keep them in git. To share songs, you export, send and re-import
  them, and end up with duplicates.
- **Extra work for nothing.** To show `Easter/sunrise.jpg` you first "import" it, which creates a database row
  that only says "there is a file at `Easter/sunrise.jpg`". The folder structure you already made is replaced by
  OpenLP's own groups, and you keep both in sync by hand.
- **Fragile.** A broken or out-of-date database (for example after an upgrade) can hide a library that is still
  sitting safely on disk.

## The solution

Point the plugin at a folder. Whatever is in that folder is the library.

- The library shows the folder as a tree: subfolders first, in natural order (`2` before `10`).
- Changes on disk appear at once. Copy files in with Explorer, sync them with OneDrive or Dropbox, or pull them
  from git, and the library updates itself.
- Everything you do in OpenLP is a normal file operation: adding copies files into the folder, dragging moves
  them, "Add folder" makes a real folder, and deleting moves files to the recycle bin. Nothing is ever
  overwritten.
- Songs are plain OpenLyrics files. OpenLP can read and edit them, and so can other programs and text editors.
- In portable mode, a library folder inside the portable folder is saved as a relative path, so you can move the
  whole folder to another drive or computer and it keeps working.

## Installation

Download the latest release from the [Releases](https://github.com/takutta/openlp-folder-plugins/releases) page.
Both files come with a Finnish install guide (`ASENNUSOHJE.txt`).

**Windows installer:** close OpenLP and run `openlp-folder-plugins-<version>-setup.exe`. It needs no
administrator rights. Windows may warn that the installer is not signed: choose "More info" and "Run anyway".
You can uninstall the plugins in Windows Settings under Apps.

**Zip, any system:** close OpenLP and copy the five folders in the `plugins` folder of the zip into OpenLP's
community plugin folder. Create the folder if it doesn't exist.

| System | Community plugin folder |
| --- | --- |
| Windows | `%APPDATA%\openlp\data\contrib\plugins` |
| Linux | `~/.local/share/openlp/contrib/plugins` |
| macOS | `~/Library/Application Support/openlp/Data/contrib/plugins` |

OpenLP looks for community plugins in this folder even when it runs in portable mode.

**Then, in OpenLP:**

1. Open **Settings → Manage Plugins** and set the folder plugins you want to **Active**. New plugins start
   inactive.
2. If you use Presentation Folder, set the original Presentations plugin to inactive. Leave the other original
   plugins installed (active or not), because the folder plugins use their code.
3. In each new library, click **Choose folder** in the toolbar and pick your folder.

To move your songs, export them from the Songs plugin with **File → Export → Song** into a folder, and choose that
folder in Song Folder.

## How it works

### Shared library

All four plugins use the same base class (`plugins/filesystem_library/`). It handles:

- **The tree.** Folders come first, in natural order, and hidden files are skipped. Expanded folders and the
  selection stay as they are when the tree reloads.
- **Watching the disk.** A file system watcher reloads the tree half a second after the last change.
- **File operations.** Adding (from a dialog or by drag and drop) copies files into the selected folder. Dragging
  inside the library moves files on disk. Deleting asks first and then moves files to the recycle bin. If a file
  with the same name already exists, it stays where it is and you are told.
- **Related files.** A file can bring other files with it that are not shown in the tree. For example, a song's
  background audio is copied, moved and deleted together with the song.
- **Adding a folder to the service.** Selecting a folder adds every file in it. Images are added as a single
  item that can loop.
- **Remote control.** The web remote can search the library, show items live and add them to the service, but it
  only gets to files inside the library folder.
- **OpenLP 3.1 and 4.** `compat.py` uses the Qt binding of the running OpenLP (PyQt5 in 3.1, PySide6 in 4) and
  the helpers that only OpenLP 4 has.

### Media Folder

Lists all the audio and video formats that OpenLP can play, whatever the case of the file extension. Network and
device streams are left out because they are not files.

### Image Folder

Works like the original Images plugin, including the background replace and reset buttons and its settings page.
Thumbnails are cached under OpenLP's data folder, named by the image's path, so no database is needed to find
them.

### Presentation Folder

Uses the original plugin's controllers (PDF, LibreOffice Impress and PowerPoint) and settings. PDFs are shown as
images, as in the original plugin. Loading the library doesn't open any presentations, because starting
LibreOffice or PowerPoint for every file in a folder would be far too slow. A thumbnail appears once you have
previewed, shown or added a presentation.

### Song Folder

Each song is an [OpenLyrics](https://docs.openlyrics.org) file, the open XML format that OpenLP uses to export
songs. Other worship programs can read it, and so can you.

- **Search.** Type in the search box above the tree to search titles, authors, lyrics, songbooks, topics,
  copyright, CCLI number, comments and file names. Only folders that contain matches are shown. The search index
  is kept in memory and cached on disk. A file is only read again when its size or modification time changes, so
  large libraries load quickly.
- **Display.** Songs use the original Songs plugin's settings, footer template and chord support, so they look
  the same as before. Verse order, forced and optional slide breaks, formatting tags and song usage logging
  work as usual. In OpenLP 4, the first line of the next slide can be shown too.
- **Editing.** "New" and "Edit" open a song editor. Lyrics are edited as a single text, with a line such as
  `---[Verse:1]---` at the start of each verse, like the "Edit All" view in the Songs plugin. You can transpose
  chords, choose a theme and choose background audio. Edited songs are also updated in the service.
- **Safe saving.** Only the fields that the editor changes are rewritten. Everything else in the file (tempo, key,
  publisher, other programs' elements and attributes) is kept. Files are written to a temporary file and then
  swapped in, so a failed save never damages the old file. If the file changed on disk while you were editing
  it, you are asked before it is overwritten.
- **Background audio.** An audio file next to the song with the same name (`Amazing Grace.mp3` for
  `Amazing Grace.xml`) plays as the song's background audio.
- **Themes.** OpenLyrics has no field for a theme, so it is saved in its own namespace
  (`<openlp:theme xmlns:openlp="http://openlp.org/ns/song-folder">`). Other programs ignore it.

## Known limitations

- LibreOffice and PowerPoint have only been tested with mocks and by starting OpenLP, not by showing a
  presentation.
- A few remote API calls only work for the original plugins, because OpenLP's core checks the plugin name: media
  play/pause/stop and transposing the live song.
- Song Folder uses the settings page of the Songs plugin, so the page appears twice if both are active.
- Translations: Finnish only so far.

## Development

OpenLP is a git submodule in `upstream/`, pinned to the release the plugins are tested against (3.1.7). The tests
use OpenLP's own fixtures and test resources from there. See [AGENTS.md](AGENTS.md) for the details (in Finnish).

```sh
git clone --recurse-submodules https://github.com/takutta/openlp-folder-plugins.git
cd openlp-folder-plugins
uv venv --python 3.11 && uv pip install -r requirements.txt
QT_QPA_PLATFORM=offscreen .venv/Scripts/python -m pytest      # .venv/bin/python on Linux and macOS
.venv/Scripts/python tools/build.py                           # dist/*.zip, and the .exe if Inno Setup is installed
```

## License

GPL-3.0-or-later, the same as OpenLP. See [LICENSE](LICENSE). OpenLP is © OpenLP Developers.
