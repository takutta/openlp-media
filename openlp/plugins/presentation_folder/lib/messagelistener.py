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
The message listener of the Presentation Folder plugin
"""
from PySide6 import QtCore

from openlp.core.common.registry import Registry
from openlp.plugins.presentations.lib.messagelistener import Controller, MessageListener


class FolderMessageListener(MessageListener):
    """
    The message listener of the Presentation plugin. The slide controller sends its messages to
    ``<service item name>_<event>``, so this listener registers under the name of the plugin it belongs to instead of
    ``presentations``.
    """
    def _setup(self, media_item):
        """
        Register the handlers under the name of the plugin

        :param media_item: The media item of the plugin
        """
        self.controllers = media_item.controllers
        self.media_item = media_item
        self.preview_handler = Controller(False)
        self.live_handler = Controller(True)
        # messages are sent from core.ui.slidecontroller
        handlers = {
            'start': self.startup,
            'stop': self.shutdown,
            'hide': self.hide,
            'first': self.first,
            'previous': self.previous,
            'next': self.next,
            'last': self.last,
            'slide': self.slide,
            'blank': self.blank,
            'unblank': self.unblank,
            'attempt_screenshot': self.attempt_live_screenshot,
        }
        for event, handler in handlers.items():
            Registry().register_function('{name}_{event}'.format(name=media_item.plugin.name, event=event), handler)
        self.timer = QtCore.QTimer()
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.timeout)
