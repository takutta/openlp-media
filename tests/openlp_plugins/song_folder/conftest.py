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
Fixtures for the tests of the file system plugins
"""
from unittest.mock import patch

import pytest

from openlp.core.lib.formattingtags import FormattingTags


@pytest.fixture(autouse=True)
def stop_leaked_patches():
    """
    Stop patches that other tests started and forgot to stop. These tests create real media manager items, and
    tests/openlp_core/lib/test_mediamanageritem.py leaves MediaManagerItem._setup patched (it calls
    ``setup_patcher.stop`` without parentheses). Fixing it here keeps the core tests untouched.
    """
    patch.stopall()
    yield


@pytest.fixture(autouse=True)
def restore_formatting_tags():
    """
    Reading a song adds its unknown formatting tags to the global list of formatting tags. Restore the list, so that
    the tests of the Songs plugin get the tags they expect.
    """
    html_expands = list(FormattingTags.html_expands)
    yield
    FormattingTags.html_expands = html_expands
