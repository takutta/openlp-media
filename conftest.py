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
The tests run against the OpenLP in the ``upstream`` submodule. The plugins are added to its ``openlp.plugins``
package, so that they can be imported as ``openlp.plugins.song_folder`` and so on, and the fixtures and test
resources of OpenLP (``tests.conftest``, ``tests.utils``) are used as they are.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO / 'upstream'))

import openlp.plugins  # noqa: E402

openlp.plugins.__path__.append(str(REPO / 'plugins'))

from openlp.core.lib.formattingtags import FormattingTags  # noqa: E402

pytest_plugins = ['tests.conftest']


@pytest.fixture(autouse=True)
def restore_formatting_tags():
    """
    Reading a song adds its unknown formatting tags to the global list of formatting tags. Restore the list, so that
    the tests do not depend on each other.
    """
    html_expands = list(FormattingTags.html_expands)
    yield
    FormattingTags.html_expands = html_expands
