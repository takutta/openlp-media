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
Start OpenLP with the file system plugins active, exercise them and print the results. This is not a pytest test, run
it by hand when the plugins or OpenLP have changed (see AGENTS.md):

    QT_QPA_PLATFORM=offscreen QTWEBENGINE_CHROMIUM_FLAGS=--no-sandbox \\
        uv run python tests/openlp_plugins/smoke_filesystem_plugins.py <empty work folder>

The work folder holds the portable data and the library, and is deleted first.
"""
import faulthandler
import os
import shutil
import sys
import threading
import traceback
from pathlib import Path

work = Path(sys.argv[1]).resolve()
repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo))
sys.argv = ['run_openlp.py', '-p', '-P', str(work / 'portable'), '-w', '-e', '-l', 'debug']
if work.exists() and any(work.iterdir()) and not (work / 'portable').is_dir():
    sys.exit(f'{work} is not empty and was not made by this script, refusing to delete it')
shutil.rmtree(work, ignore_errors=True)
library = work / 'library'
(library / 'images' / 'Easter').mkdir(parents=True)
(library / 'presentations').mkdir(parents=True)
(library / 'media').mkdir(parents=True)
shutil.copy(repo / 'tests/resources/presentations/pdf_test1.pdf', library / 'presentations' / 'welcome.pdf')
(work / 'portable' / 'Data').mkdir(parents=True)

from PySide6 import QtCore, QtGui, QtWidgets  # noqa: E402

from openlp.core.common.settings import Settings  # noqa: E402
from openlp.core.version import get_version  # noqa: E402

Settings.setDefaultFormat(Settings.IniFormat)
Settings.set_filename(work / 'portable' / 'Data' / 'OpenLP.ini')
settings = Settings()
settings.setValue('core/has run wizard', True)
settings.setValue('settings/version', 4)
settings.setValue('core/show splash', False)
settings.setValue('core/application version', get_version()['version'])
settings.setValue('core/language', 'fi')
for name, folder in (('image_folder', 'images'), ('presentation_folder', 'presentations'),
                     ('media_folder', 'media')):
    settings.setValue(f'{name}/status', 1)
    settings.setValue(f'{name}/root folder', library / folder)
settings.sync()
del settings

results = []


def on_timeout():
    print('WATCHDOG TIMEOUT', flush=True)
    faulthandler.dump_traceback(all_threads=True)
    os._exit(3)


watchdog = threading.Timer(120, on_timeout)
watchdog.daemon = True
watchdog.start()


def check(name, condition):
    results.append((name, bool(condition)))
    print(('OK   ' if condition else 'FAIL ') + name, flush=True)


def wait(seconds):
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(int(seconds * 1000), loop.quit)
    loop.exec()


def find_item(media_item, path):
    iterator = QtWidgets.QTreeWidgetItemIterator(media_item.list_view)
    while iterator.value():
        if iterator.value().data(0, QtCore.Qt.ItemDataRole.UserRole) == path:
            return iterator.value()
        iterator += 1


def exercise():
    from openlp.core.common.registry import Registry
    try:
        pm = Registry().get('plugin_manager')
        plugins = {name: pm.get_plugin_by_name(name) for name in ('image_folder', 'presentation_folder',
                                                                  'media_folder')}
        for name, plugin in plugins.items():
            check(f'{name} active with media item', plugin and plugin.is_active() and plugin.media_item)
        if (repo / 'openlp' / 'plugins' / 'image_folder' / 'i18n' / 'fi.qm').exists():
            check('finnish plugin name', plugins['image_folder'].name_strings['singular'] == 'Kuvakansio')
            check('finnish base class text',
                  plugins['image_folder'].media_item.choose_root_action.text() == 'Valitse kansio')
        else:
            print('SKIP finnish texts, the .qm files have not been compiled', flush=True)
        images = plugins['image_folder'].media_item
        # Images appear through the file system watcher
        for name in ('a.png', 'Easter/b.png', 'Easter/c.png'):
            image = QtGui.QImage(64, 48, QtGui.QImage.Format.Format_RGB32)
            image.fill(QtGui.QColor('green'))
            image.save(str(library / 'images' / name))
        wait(2)
        check('watcher picked up images', len(images.get_file_list()) == 3)
        service_manager = Registry().get('service_manager')
        live = Registry().get('live_controller')
        find_item(images, library / 'images' / 'Easter').setSelected(True)
        images.on_add_click()
        check('image folder added to service', len(service_manager.service_items) == 1)
        image_item = service_manager.service_items[0]['service_item']
        check('image service item has 2 slides', len(image_item.slides) == 2)
        images.go_live(str(library / 'images' / 'a.png'))
        check('image live', live.service_item and live.service_item.name == 'image_folder')
        presentations = plugins['presentation_folder'].media_item
        pdf = library / 'presentations' / 'welcome.pdf'
        check('pdf listed', presentations.get_file_list() == [pdf])
        check('display types', presentations.display_type_combo_box.count() >= 1)
        presentations.add_to_service(find_item(presentations, pdf))
        check('pdf added to service', len(service_manager.service_items) == 2)
        pdf_item = service_manager.service_items[1]['service_item']
        check('pdf service item is a command', pdf_item.is_command() and len(pdf_item.slides) == 3)
        # Send the PDF from the service live, the message listener turns it into images
        service_manager.set_item(1)
        service_manager.make_live()
        wait(1)
        check('pdf live as images', live.service_item and live.service_item.is_image()
              and len(live.service_item.slides) == 3)
        # Save and load the service
        service_file = work / 'test.osz'
        service_manager.set_file_name(service_file)
        service_manager.save_file()
        check('service saved', service_file.exists())
        service_manager.new_file()
        service_manager.load_file(service_file)
        wait(1)
        items = [item['service_item'] for item in service_manager.service_items]
        check('service loaded', [item.name for item in items] == ['image_folder', 'presentation_folder'])
        check('icons after load', all(item.icon is not None and not item.icon.isNull() for item in items))
        thumbnail = Path(items[1].slides[0]['image'])
        check(f'pdf thumbnails after load ({thumbnail})', thumbnail.is_absolute() and thumbnail.exists())
        check('image valid after load', items[0].is_valid and len(items[0].slides) == 2)
        service_manager.set_item(1)
        service_manager.make_live()
        wait(1)
        check('loaded pdf live as images', live.service_item and live.service_item.is_image())
        # Remote API search and live
        from openlp.core.api.versions.v2.plugins import search
        found = search('presentation_folder', 'welc')
        check('remote search', found == [[str(pdf), 'welcome.pdf']])
        getattr(images, 'image_folder_go_live').emit([str(library / 'images' / 'Easter' / 'c.png'), True])
        wait(0.5)
        check('remote live', live.service_item.title == 'c.png')
    except Exception:
        traceback.print_exc()
        check('no exception', False)
    failed = [name for name, ok in results if not ok]
    print('SMOKE RESULT:', 'FAILED ' + ', '.join(failed) if failed else 'ALL OK', flush=True)
    sys.stdout.flush()
    os._exit(1 if failed else 0)


from openlp.core import app as app_module  # noqa: E402

original_run = app_module.OpenLP.run


def run(self, args, application):
    QtCore.QTimer.singleShot(3000, exercise)
    return original_run(self, args, application)


app_module.OpenLP.run = run
os.chdir(repo)
app_module.main()
