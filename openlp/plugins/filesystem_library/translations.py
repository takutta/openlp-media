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
Loads the translations of the file system plugins. The translations are kept next to the plugins instead of the
translation files of OpenLP, so that updating OpenLP does not touch them.
"""
import logging
from pathlib import Path
from typing import Dict

from PySide6 import QtCore

from openlp.core.common.i18n import LanguageManager


log = logging.getLogger(__name__)

# The folder of the translations of the shared library code
LIBRARY_TRANSLATIONS_PATH = Path(__file__).parent / 'i18n'

# The installed translators need to be kept alive, otherwise Qt forgets them
_translators: Dict[Path, QtCore.QTranslator] = {}


def install_translator(translations_path: Path) -> bool:
    """
    Install the translation of the current language from a folder, for example ``i18n/fi.qm``. Does nothing if the
    folder has no translation for the current language or if it has already been installed.

    Call this before any translated texts are created, i.e. at the start of the constructor of the plugin.

    :param translations_path: The folder containing the compiled translation files
    :return: True if a translation was installed
    """
    application = QtCore.QCoreApplication.instance()
    if application is None or translations_path in _translators:
        return False
    try:
        language = LanguageManager.get_language()
    except Exception:
        log.exception('Could not get the language of OpenLP')
        return False
    translator = QtCore.QTranslator()
    if not translator.load(language, str(translations_path)):
        log.debug(f'No "{language}" translation in {translations_path}')
        return False
    application.installTranslator(translator)
    _translators[translations_path] = translator
    log.info(f'Translation "{language}" loaded from {translations_path}')
    return True
