"""
    verktyg.testsuite.accept
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for choosing representations based on content type, etc.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from verktyg.accept import Representation


class RepresentationTestCase(WerkzeugTestCase):
    def test_content_type_dispatch(self):
        default_binding = Representation()
        html_binding = Representation(content_type='text/html')

        self.assert_equal(
            (5, 0.001),
            default_binding.quality(accept='text/html'))

        self.assert_equal(
            (110, 1.0),
            html_binding.quality(accept='text/html'))

        self.assert_equal(
            (110, 0.9),
            html_binding.quality(accept='text/html;q=0.9'))

        self.assert_equal(
            (0, 0.01),
            html_binding.quality(accept='text/json, */*; q=0.01'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RepresentationTestCase))
    return suite
