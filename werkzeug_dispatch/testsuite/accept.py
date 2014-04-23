"""
    werkzeug_dispatch.testsuite.accept
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for choosing representations based on content type, etc.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug_dispatch.accept import Representation


class RepresentationTestCase(WerkzeugTestCase):
    def test_content_type_dispatch(self):
        default_binding = Representation()
        html_binding = Representation(content_type='text/html')

        self.assert_equal(
            0.001,
            default_binding.quality(accept='text/html'))

        self.assert_equal(
            1.0,
            html_binding.quality(accept='text/html'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RepresentationTestCase))
    return suite
