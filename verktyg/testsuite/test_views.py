"""
    verktyg.testsuite.views
    ~~~~~~~~~~~~~~~~~~~~~~~

    Tests for view wrappers.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

import verktyg
from verktyg.exceptions import MethodNotAllowed
import verktyg.views as vtv


class ViewsTestCase(unittest.TestCase):
    def test_decorators(self):
        dispatcher = verktyg.Dispatcher()

        @vtv.expose(dispatcher, 'foo')
        def foo(env, req):
            pass

    def test_class_view(self):
        dispatcher = verktyg.Dispatcher()

        class Foo(vtv.ClassView):
            name = 'foo'

            def GET(self, env, req):
                return 'get'

            def POST(self, env, req):
                return 'post'

        dispatcher.add_bindings(Foo())

        self.assertEqual(
            'get',
            dispatcher.lookup('foo', method='GET')(None, None)
        )
        self.assertEqual(
            'post',
            dispatcher.lookup('foo', method='POST')(None, None)
        )
        self.assertRaises(
            MethodNotAllowed,
            dispatcher.lookup, 'foo', method='PUT'
        )


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ViewsTestCase))
    return suite
