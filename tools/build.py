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
Build the release files into dist/:

    openlp-folder-plugins-<version>.zip         the plugins, the install guides and tools/migrate_database.py
    openlp-folder-plugins-<version>-setup.exe   the Windows installer, if Inno Setup (ISCC) is installed

    python tools/build.py [--translations-only]

The translations (.qm) are compiled next to their .ts files first, which is also what running the plugins from
source needs. lrelease comes from PySide6, with uvx if it is not installed.
"""
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / 'dist'
VERSION = (REPO / 'VERSION').read_text(encoding='utf-8').strip()
NAME = f'openlp-folder-plugins-{VERSION}'


def lrelease_command():
    for name in ('pyside6-lrelease', 'lrelease'):
        if shutil.which(name):
            return [name]
    return ['uvx', '--from', 'pyside6-essentials', 'pyside6-lrelease']


def compile_translations():
    command = lrelease_command()
    # Python of this virtual environment must not leak to the Python of uvx
    env = {key: value for key, value in os.environ.items()
           if key not in ('__PYVENV_LAUNCHER__', 'PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV')}
    for ts_path in sorted((REPO / 'plugins').glob('*/i18n/*.ts')):
        subprocess.run(command + [str(ts_path), '-qm', str(ts_path.with_suffix('.qm'))], check=True,
                       stdout=subprocess.DEVNULL, env=env)
        print('compiled', ts_path.relative_to(REPO))


def find_iscc():
    found = shutil.which('ISCC')
    if found:
        return found
    for path in (Path.home() / 'scoop' / 'apps' / 'inno-setup' / 'current' / 'ISCC.exe',
                 Path('C:/Program Files (x86)/Inno Setup 6/ISCC.exe'), Path('C:/Program Files/Inno Setup 6/ISCC.exe')):
        if path.exists():
            return str(path)
    return None


def stage() -> Path:
    stage_dir = DIST / 'stage'
    shutil.rmtree(stage_dir, ignore_errors=True)
    for plugin_path in sorted((REPO / 'plugins').iterdir()):
        shutil.copytree(plugin_path, stage_dir / 'plugins' / plugin_path.name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.ts'))
    # Notepad and the installer both read Windows line endings
    for name, placeholder in (('INSTALL.txt', '<version>'), ('ASENNUSOHJE.txt', '<versio>')):
        guide = (REPO / 'tools' / name).read_text(encoding='utf-8').replace(placeholder, VERSION)
        (stage_dir / name).write_text(guide, encoding='utf-8-sig', newline='\r\n')
    shutil.copy(REPO / 'LICENSE', stage_dir / 'LICENSE.txt')
    # Only in the zip, the installer installs the plugins folder
    (stage_dir / 'tools').mkdir()
    shutil.copy(REPO / 'tools' / 'migrate_database.py', stage_dir / 'tools')
    return stage_dir


def make_zip(stage_dir: Path) -> Path:
    zip_path = DIST / f'{NAME}.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(stage_dir.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(stage_dir))
    return zip_path


def make_installer(stage_dir: Path):
    iscc = find_iscc()
    if not iscc:
        print('Inno Setup (ISCC) was not found, the installer was not made')
        return None
    subprocess.run([iscc, '/Q', f'/DAppVersion={VERSION}', f'/DStageDir={stage_dir}', f'/DOutputDir={DIST}',
                    str(REPO / 'tools' / 'installer.iss')], check=True)
    return DIST / f'{NAME}-setup.exe'


def main():
    compile_translations()
    if '--translations-only' in sys.argv:
        return
    DIST.mkdir(exist_ok=True)
    stage_dir = stage()
    for result in (make_zip(stage_dir), make_installer(stage_dir)):
        if result:
            print('made', result.relative_to(REPO))


if __name__ == '__main__':
    main()
