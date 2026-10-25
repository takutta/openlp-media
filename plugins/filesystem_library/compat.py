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
The differences between OpenLP 3.1 (PyQt5) and OpenLP 4 (PySide6), so that the same plugins run on both.
Import Qt from here, never from PyQt5 or PySide6 directly.
"""
import sys

# The core of OpenLP has imported its Qt binding by now, and the plugins must use the same one
import openlp.core.common.settings  # noqa: F401

if 'PySide6' in sys.modules:
    from PySide6 import QtCore, QtGui, QtWidgets
    Signal = QtCore.Signal
    Slot = QtCore.Slot
else:
    from PyQt5 import QtCore, QtGui, QtWidgets
    Signal = QtCore.pyqtSignal
    Slot = QtCore.pyqtSlot

try:
    # OpenLP 4 asks Qt Multimedia what it can play
    from openlp.core.ui.media import get_supported_media_suffix
except ImportError:
    from openlp.core.ui.media import AUDIO_EXT, VIDEO_EXT

    def get_supported_media_suffix():
        """
        The audio and video suffixes (``*.mp3``) which OpenLP can play, as ``(audio, video)``
        """
        return AUDIO_EXT, VIDEO_EXT

try:
    # Case-insensitive on Linux and macOS
    from openlp.core.common import get_file_type_glob
except ImportError:
    def get_file_type_glob(extension: str) -> str:
        return '*.' + extension

__all__ = ['QtCore', 'QtGui', 'QtWidgets', 'Signal', 'Slot', 'get_supported_media_suffix', 'get_file_type_glob']
