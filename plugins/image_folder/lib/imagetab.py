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
The settings tab of the Image Folder plugin
"""
from openlp.core.lib.ui import find_and_set_in_combo_box
from openlp.plugins.images.lib.imagetab import ImageTab


class ImageFolderTab(ImageTab):
    """
    The settings tab of the Image plugin, but using the settings of the plugin this tab belongs to
    """
    def update_theme_list(self, theme_list):
        """
        Called from ThemeManager when the Themes have changed.

        :param theme_list: The list of available themes
        """
        self.image_theme = self.settings.value(self.tab_title + '/theme')
        self.theme_combo_box.clear()
        self.theme_combo_box.addItems(theme_list)
        find_and_set_in_combo_box(self.theme_combo_box, self.image_theme)

    def load(self):
        self.background_mode = self.settings.value(self.tab_title + '/background mode')
        self.initial_mode = self.background_mode
        self.radio_group.button(self.background_mode).setChecked(True)
        self.image_theme = self.settings.value(self.tab_title + '/theme')
        self.initial_theme = self.image_theme

    def save(self):
        self.settings.setValue(self.tab_title + '/background mode', self.radio_group.checkedId())
        self.settings.setValue(self.tab_title + '/theme', self.image_theme)
        if self.initial_theme != self.image_theme or self.initial_mode != self.background_mode:
            self.settings_form.register_post_process(self.tab_title + '_config_updated')
