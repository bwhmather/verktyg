# -*- coding: utf-8 -*-
"""
    verktyg.testsuite.views
    ~~~~~~~~~~~~~~~~~~~~~~~

    Tests for view wrappers.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug.wrappers import Response
from werkzeug.exceptions import MethodNotAllowed

import verktyg
import verktyg.views as vtv


class ViewsTestCase(WerkzeugTestCase):
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

        self.assert_equal('get',
                          dispatcher.lookup('foo', method='GET')(None, None))
        self.assert_equal('post',
                          dispatcher.lookup('foo', method='POST')(None, None))
        self.assert_raises(MethodNotAllowed,
                           dispatcher.lookup, 'foo', method='PUT')

    def test_template_view(self):
        dispatcher = verktyg.Dispatcher()

        class HelloEnv(object):
            def get_renderer(self, name):
                if name == 'hello':
                    return lambda res: Response('hello %s' % res)
        env = HelloEnv()

        @vtv.expose_html(dispatcher, 'say-hello', template='hello')
        def say_hello(env, req):
            return 'world'

        @vtv.expose_html(dispatcher, 'returns-response', template='hello')
        def returns_response(env, req):
            return Response('too slow')

        self.assert_equal(
            b'hello world',
            dispatcher.lookup('say-hello')(env, None).get_data())
        self.assert_equal(
            b'too slow',
            dispatcher.lookup('returns-response')(env, None).get_data())


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ViewsTestCase))
    return suite
