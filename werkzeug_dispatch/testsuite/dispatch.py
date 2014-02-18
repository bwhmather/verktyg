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
from werkzeug.datastructures import Accept
from werkzeug.exceptions import NotFound, MethodNotAllowed, NotAcceptable


class DispatchTestCase(WerkzeugTestCase):
    def test_name_dispatch(self):
        dispatcher = d.Dispatcher([
            d.Binding('tweedle-dum', 'Tweedle Dum'),
            d.Binding('tweedle-dee', 'Tweedle Dee'),
            d.Binding('same', 'overridden'),
            d.Binding('same', 'overriding'),
            ])

        self.assert_equal('Tweedle Dum', dispatcher.lookup('tweedle-dum'))
        self.assert_equal('Tweedle Dee', dispatcher.lookup('tweedle-dee'))
        self.assert_raises(NotFound, dispatcher.lookup, 'non-existant')
        self.assert_equal('overriding', dispatcher.lookup('same'))

    def test_method_dispatch(self):
        dispatcher = d.Dispatcher([
            d.Binding('test', 'get', method='GET'),
            d.Binding('test', 'post', method='POST'),
            d.Binding('head', 'head', method='HEAD'),
            d.Binding('no-head', 'get', method='GET'),

            d.Binding('same', 'overridden'),
            d.Binding('same', 'unaffected', method='POST'),
            d.Binding('same', 'overriding'),
            ])

        # default to 'GET'
        self.assert_equal('get', dispatcher.lookup('test'))
        self.assert_equal('get', dispatcher.lookup('test', method='GET'))

        # `POST` gives something different
        self.assert_equal('post', dispatcher.lookup('test', method='POST'))

        # `PUT` not found
        self.assert_raises(MethodNotAllowed, dispatcher.lookup, 'test', method='PUT')

        # `HEAD` should fall back to `GET`
        self.assert_equal('head', dispatcher.lookup('head', method='HEAD'))
        self.assert_equal('get', dispatcher.lookup('no-head', method='HEAD'))

        # replacing handler for one method should not affect others
        self.assert_equal('overriding', dispatcher.lookup('same'))
        self.assert_equal('unaffected', dispatcher.lookup('same', method='POST'))

    def test_accept_dispatch(self):
        dispatcher = d.Dispatcher([
            d.Binding('test', 'text/json', content_type='text/json'),
            d.Binding('test', 'text/html', content_type='text/html'),
#            d.Binding('test', 'catch-all', content_type='*'), TODO
            ])

        # werkzeug accept objects
        self.assert_equal('text/json',
            dispatcher.lookup('test', accept=Accept([('text/json', 1.0)])))
        self.assert_equal('text/html',
            dispatcher.lookup('test', accept=Accept([('text/html', 1.0)])))
# TODO
#        self.assert_equal('text/json',
#            dispatcher.lookup('test', accept=Accept([('application/html', 1.0)])))

        # accept header strings
        self.assert_equal('text/json',
            dispatcher.lookup('test', accept='text/json'))

        self.assert_equal('text/json',
            dispatcher.lookup('test', accept='text/json; q=0.9, text/html; q=0.8'))

    def test_decorators(self):
        dispatcher = d.Dispatcher()

        @dispatcher.expose('foo')
        def foo(env, req):
            pass

    def test_class_view(self):
        dispatcher = d.Dispatcher(default_view=d.View)

        class Foo(d.ClassView):
            name = 'foo'

            def GET(self, env, req):
                return 'get'

            def POST(self, env, req):
                return 'post'

        dispatcher.add(Foo())

        self.assert_equal('get', dispatcher.lookup('foo', method='GET')(None, None))
        self.assert_equal('post', dispatcher.lookup('foo', method='POST')(None, None))
        self.assert_raises(MethodNotAllowed, dispatcher.lookup, 'foo', method='PUT')


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

        self.assert_equal(
            b'hello world',
            dispatcher.lookup('say-hello')(env, None).get_data())
        self.assert_equal(
            b'too slow',
            dispatcher.lookup('returns-response')(env, None).get_data())

    def test_nested(self):
        child = d.Dispatcher([
            d.Binding('nested', 'Nested'),
            ])
        parent = d.Dispatcher([
            child,
            ])

        self.assert_equal(
            'Nested',
            parent.lookup('nested'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DispatchTestCase))
    return suite
