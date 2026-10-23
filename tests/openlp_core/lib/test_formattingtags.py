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
Package to test the openlp.core.lib.formattingtags package.
"""
import copy
from unittest.mock import patch

from openlp.core.lib.formattingtags import FormattingTags


TAG = {
    'end tag': '{/aa}',
    'start html': '<span>',
    'start tag': '{aa}',
    'protected': False,
    'end html': '</span>',
    'desc': 'name'
}


def test_get_html_tags_no_user_tags(mock_settings):
    """
    Test the FormattingTags class' get_html_tags static method.
    """
    with patch('openlp.core.lib.translate') as mocked_translate, \
            patch('openlp.core.common.settings') as mocked_settings, \
            patch('openlp.core.lib.formattingtags.json') as mocked_json:
        # GIVEN: Our mocked modules and functions.
        mocked_translate.side_effect = lambda module, string_to_translate, comment: string_to_translate
        mocked_settings.value.return_value = ''
        mocked_json.load.return_value = []

        # WHEN: Get the display tags.
        FormattingTags.load_tags()
        old_tags_list = copy.deepcopy(FormattingTags.get_html_tags())
        FormattingTags.load_tags()
        new_tags_list = FormattingTags.get_html_tags()

        # THEN: Lists should be identical.
        assert old_tags_list == new_tags_list, 'The formatting tag lists should be identical.'


def test_get_html_tags_with_user_tags(mock_settings):
    """
    FormattingTags class - test the get_html_tags(), add_html_tags() and remove_html_tag() methods.
    """
    with patch('openlp.core.lib.translate') as mocked_translate, \
            patch('openlp.core.lib.formattingtags.json') as mocked_json:
        # GIVEN: Our mocked modules and functions.
        mocked_translate.side_effect = lambda module, string_to_translate: string_to_translate
        mock_settings.value.return_value = ''
        mocked_json.loads.side_effect = [[], [TAG]]

        # WHEN: Get the display tags.
        FormattingTags.load_tags()
        old_tags_list = copy.deepcopy(FormattingTags.get_html_tags())

        # WHEN: Add our tag and get the tags again.
        FormattingTags.load_tags()
        FormattingTags.add_html_tags([TAG])
        new_tags_list = copy.deepcopy(FormattingTags.get_html_tags())

        # THEN: Lists should not be identical.
        assert old_tags_list != new_tags_list, 'The lists should be different.'

        # THEN: Added tag and last tag should be the same.
        new_tag = new_tags_list.pop()
        assert TAG == new_tag, 'Tags should be identical.'

        # WHEN: Remove the new tag.
        FormattingTags.remove_html_tag(len(new_tags_list))

        # THEN: The lists should now be identical.
        assert old_tags_list == FormattingTags.get_html_tags(), 'The lists should be identical.'


def test_preview_tag_uses_style_html_from_settings(mock_settings):
    """
    Test that load_tags() uses 'songs/preview_style_html' directly
    for the {preview} tag's start HTML.
    """
    with patch('openlp.core.lib.translate') as mocked_translate, \
         patch('openlp.core.lib.formattingtags.json') as mocked_json:

        # GIVEN: Our mocked modules and functions.
        mocked_translate.side_effect = lambda module, text, *args, **kwargs: text
        mocked_json.load.return_value = []

        # GIVEN: Settings return the formatted style HTML string
        expected_html = '<span style="opacity: 0.45; font-size: 75%;">'
        mock_settings.value.side_effect = lambda key, default=None: (
            expected_html if key == 'songs/preview_style_html' else default
        )
        # WHEN: Tags are loaded
        FormattingTags.load_tags()
        tags = FormattingTags.get_html_tags()
        preview_tag = next(t for t in tags if t['start tag'] == '{preview}')

        # THEN: The start html matches the mocked setting, and is protected
        assert preview_tag['start html'] == expected_html
        assert preview_tag['protected'] is True
