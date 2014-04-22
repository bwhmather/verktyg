"""
    werkzeug_dispatch.testsuite.bindings
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for individual bindings.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug_dispatch.bindings import Binding


class BindingsTestCase(WerkzeugTestCase):
    def test_attributes(self):
        self.assert_equal(
            'endpoint',
            Binding('endpoint', 'action').name)

        self.assert_equal(
            'action',
            Binding('endpoint', 'action').action)

        self.assert_equal(
            'POST',
            Binding('endpoint', 'action', method='POST').method)

        # default to `GET`
        self.assert_equal(
            'GET',
            Binding('endpoint', 'action').method)

    def test_content_type_dispatch(self):
        default_binding = Binding('e', 'a')
        html_binding = Binding('e', 'a', content_type='text/html')

        self.assert_equal(
            0.001,
            default_binding.quality(accept='text/html'))

        self.assert_equal(
            1.0,
            html_binding.quality(accept='text/html'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(BindingsTestCase))
    return suite
