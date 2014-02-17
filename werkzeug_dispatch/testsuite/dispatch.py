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


class DispatchTestCase(WerkzeugTestCase):
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

    def test_class_view(self):
        dispatcher = d.Dispatcher(default_view=d.View)

        class Foo(d.ClassView):
            name = 'foo'

            def GET(self, env, req):
                return Response('get')

            def POST(self, env, req):
                return Response('post')

        dispatcher.add(Foo())

        dispatcher.lookup('POST', 'foo')

    def test_template_view(self):
        dispatcher = d.Dispatcher(default_view=d.TemplateView)

        class HelloEnv(object):
            def get_renderer(self, name):
                if name == 'hello':
                    return lambda res: Response('hello %s' % res)
        env = HelloEnv()

        @d.expose(dispatcher, 'say-hello', template='hello')
        def say_hello(env, req):
            return 'world'

        @d.expose(dispatcher, 'returns-response', template='hello')
        def returns_response(env, req):
            return Response('too slow')

        self.assertEqual(
                b'hello world',
                dispatcher.lookup('GET', 'say-hello')(env, None).get_data())
        self.assertEqual(
                b'too slow',
                dispatcher.lookup('GET', 'returns-response')(env, None).get_data())

def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DispatchTestCase))
    return suite
