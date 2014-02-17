# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.testsuite.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for the core dispatcher.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

import werkzeug_dispatch as d
from werkzeug.wrappers import Response


class RoutingTestCase(WerkzeugTestCase):
    def test_basic_dispatch(self):
        dispatcher = d.Dispatcher([
            d.View('say-hello', lambda env, req: Response('hello')),
            d.View('say-goodbye', lambda env, req: Response('goodbye')),
        ])
        dispatcher.lookup('GET', 'say-hello')


    def test_decorators(self):
        dispatcher = d.Dispatcher()

        @dispatcher.expose('foo')
        def foo(env, req):
            pass


    def test_head_fallback(self):
        dispatcher = d.Dispatcher(default_view=d.View)

        @dispatcher.expose('get', methods={'GET'})
        def get(env, req):
            return 'get'

        self.assertEqual('get', dispatcher.lookup('HEAD', 'get')(None, None))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RoutingTestCase))
    return suite
