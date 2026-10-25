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
Test the image folder plugin and its settings tab
"""
from unittest.mock import MagicMock

from openlp.core.common.enum import ImageThemeMode, PluginStatus
from openlp.core.common.registry import Registry
from openlp.core.common.settings import Settings
from openlp.plugins.image_folder.image_folder_plugin import ImageFolderPlugin
from openlp.plugins.image_folder.lib.imagetab import ImageFolderTab


def test_plugin_registers_itself(state, settings):
    """The plugin can be found under the names the State and the service manager use"""
    plugin = ImageFolderPlugin()

    assert plugin.name == 'image_folder'
    assert Registry().get('image_folder_plugin') is plugin
    assert plugin.status == PluginStatus.Inactive


def test_plugin_adds_its_own_default_settings(state, settings):
    """The plugin does not need its settings in the default settings of the core"""
    # GIVEN: Default settings without the settings of the plugin
    for key in ('image_folder/status', 'image_folder/background mode', 'image_folder/theme'):
        Settings.__default_settings__.pop(key, None)

    # WHEN: The plugin is created
    ImageFolderPlugin()

    # THEN: The plugin added the defaults itself
    assert Settings.__default_settings__['image_folder/status'] == PluginStatus.Inactive
    assert Settings.__default_settings__['image_folder/background mode'] == ImageThemeMode.Black
    assert settings.value('image_folder/theme') is None


def test_about_text():
    """The about text is not empty"""
    assert ImageFolderPlugin.about()


def test_settings_tab_uses_plugin_settings(state, settings, registry):
    """The settings tab reads and writes the settings of the image folder plugin, not of the image plugin"""
    # GIVEN: Settings of both plugins and the settings tab
    ImageFolderPlugin()
    settings.setValue('images/background mode', ImageThemeMode.CustomTheme)
    settings.setValue('image_folder/background mode', ImageThemeMode.CustomTheme)
    settings.setValue('image_folder/theme', 'Pictures')
    settings_form = MagicMock()
    registry.register('settings_form', settings_form)
    tab = ImageFolderTab(None, 'image_folder', 'Image Folder')

    # THEN: The tab shows the settings of the image folder plugin
    assert tab.custom_theme_radio.isChecked()
    tab.update_theme_list(['Default', 'Pictures'])
    assert tab.theme_combo_box.currentText() == 'Pictures'

    # WHEN: Changing them and saving
    tab.use_black_radio.setChecked(True)
    tab.save()

    # THEN: Only the image folder plugin settings are changed
    assert settings.value('image_folder/background mode') == ImageThemeMode.Black
    assert settings.value('images/background mode') == ImageThemeMode.CustomTheme
    settings_form.register_post_process.assert_called_once_with('image_folder_config_updated')
