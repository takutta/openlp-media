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
Test loading the translations of the file system plugins
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from openlp.plugins.filesystem_library import translations
from openlp.plugins.filesystem_library.translations import LIBRARY_TRANSLATIONS_PATH, install_translator


@pytest.fixture
def no_translators():
    with patch.object(translations, '_translators', {}):
        yield translations._translators


@patch('openlp.plugins.filesystem_library.translations.LanguageManager.get_language', return_value='fi')
@patch('openlp.plugins.filesystem_library.translations.QtCore.QTranslator')
@patch('openlp.plugins.filesystem_library.translations.QtCore.QCoreApplication.instance')
def test_install_translator(mocked_instance, MockedTranslator, mocked_get_language, no_translators):
    """The translation of the current language is installed once"""
    # GIVEN: A folder with a translation for the current language
    translator = MockedTranslator.return_value
    translator.load.return_value = True
    path = Path('/plugin/i18n')

    # WHEN: Installing the translator twice
    first = install_translator(path)
    second = install_translator(path)

    # THEN: It is loaded from the folder and installed only once
    assert first is True
    assert second is False
    translator.load.assert_called_once_with('fi', str(path))
    mocked_instance.return_value.installTranslator.assert_called_once_with(translator)
    assert no_translators[path] is translator


@patch('openlp.plugins.filesystem_library.translations.LanguageManager.get_language', return_value='sv')
@patch('openlp.plugins.filesystem_library.translations.QtCore.QTranslator')
@patch('openlp.plugins.filesystem_library.translations.QtCore.QCoreApplication.instance')
def test_install_translator_missing_language(mocked_instance, MockedTranslator, mocked_get_language, no_translators):
    """Nothing is installed if the folder has no translation for the current language"""
    MockedTranslator.return_value.load.return_value = False

    assert install_translator(Path('/plugin/i18n')) is False
    mocked_instance.return_value.installTranslator.assert_not_called()
    assert no_translators == {}


@patch('openlp.plugins.filesystem_library.translations.QtCore.QCoreApplication.instance', return_value=None)
def test_install_translator_without_application(mocked_instance, no_translators):
    """Nothing is installed before the application exists"""
    assert install_translator(Path('/plugin/i18n')) is False


def test_library_translations_are_included():
    """The shared library code has its Finnish translation source next to it"""
    assert (LIBRARY_TRANSLATIONS_PATH / 'fi.ts').is_file()
