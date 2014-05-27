"""
    verktyg.testsuite.views
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for view wrappers.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.testsuite import WerkzeugTestCase

from werkzeug.wrappers import Response
from werkzeug.exceptions import MethodNotAllowed

import verktyg as d


class ViewsTestCase(WerkzeugTestCase):
    def test_decorators(self):
        dispatcher = d.Dispatcher()

        @d.expose(dispatcher, 'foo')
        def foo(env, req):
            pass

    def test_class_view(self):
        dispatcher = d.Dispatcher()

        class Foo(d.ClassView):
            name = 'foo'

            def GET(self, env, req):
                return 'get'

            def POST(self, env, req):
                return 'post'

        dispatcher.add(Foo())

        self.assert_equal('get',
                          dispatcher.lookup('foo', method='GET')(None, None))
        self.assert_equal('post',
                          dispatcher.lookup('foo', method='POST')(None, None))
        self.assert_raises(MethodNotAllowed,
                           dispatcher.lookup, 'foo', method='PUT')

    def test_template_view(self):
        dispatcher = d.Dispatcher()

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
