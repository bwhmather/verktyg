"""
    tests.responses
    ~~~~~~~~~~~~~~

    Tests for response objects.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from datetime import datetime

from verktyg.http import Headers
from verktyg.test import create_environ, run_wsgi_app
from verktyg.requests import Request
from verktyg.responses import (
    BaseResponse, Response, ETagResponseMixin, generate_etag
)


class ResponsesTestCase(unittest.TestCase):
    def assert_environ(self, environ, method):
        self.assertEqual(environ['REQUEST_METHOD'], method)
        self.assertEqual(environ['PATH_INFO'], '/')
        self.assertEqual(environ['SCRIPT_NAME'], '')
        self.assertEqual(environ['SERVER_NAME'], 'localhost')
        self.assertEqual(environ['wsgi.version'], (1, 0))
        self.assertEqual(environ['wsgi.url_scheme'], 'http')

    def test_base_response(self):
        # unicode
        response = BaseResponse(u'öäü')
        self.assertEqual(response.get_data(), u'öäü'.encode('utf-8'))

        # writing
        response = Response('foo')
        response.stream.write('bar')
        self.assertEqual(response.get_data(), b'foobar')

        # set cookie
        response = BaseResponse()
        response.set_cookie('foo', 'bar', 60, 0, '/blub', 'example.org')
        self.assertEqual(response.headers.to_wsgi_list(), [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Set-Cookie', 'foo=bar; Domain=example.org; Expires=Thu, '
             '01-Jan-1970 00:00:00 GMT; Max-Age=60; Path=/blub')
        ])

        # delete cookie
        response = BaseResponse()
        response.delete_cookie('foo')
        self.assertEqual(response.headers.to_wsgi_list(), [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Set-Cookie', 'foo=; Expires=Thu, 01-Jan-1970 00:00:00 GMT; '
                           'Max-Age=0; Path=/'),
        ])

        # close call forwarding
        closed = []

        class Iterable(object):

            def __next__(self):
                raise StopIteration()

            def __iter__(self):
                return self

            def close(self):
                closed.append(True)
        response = BaseResponse(Iterable())
        response.call_on_close(lambda: closed.append(True))
        app_iter, status, headers = run_wsgi_app(response,
                                                 create_environ(),
                                                 buffered=True)
        self.assertEqual(status, '200 OK')
        self.assertEqual(''.join(app_iter), '')
        self.assertEqual(len(closed), 2)

        # with statement
        del closed[:]
        response = BaseResponse(Iterable())
        with response:
            pass
        self.assertEqual(len(closed), 1)

    def test_response_status_codes(self):
        response = BaseResponse()
        response.status_code = 404
        self.assertEqual(response.status, '404 NOT FOUND')
        response.status = '200 OK'
        self.assertEqual(response.status_code, 200)
        response.status = '999 WTF'
        self.assertEqual(response.status_code, 999)
        response.status_code = 588
        self.assertEqual(response.status_code, 588)
        self.assertEqual(response.status, '588 UNKNOWN')
        response.status = 'wtf'
        self.assertEqual(response.status_code, 0)
        self.assertEqual(response.status, '0 wtf')

    def test_type_forcing(self):
        def wsgi_application(environ, start_response):
            start_response('200 OK', [('Content-Type', 'text/html')])
            return ['Hello World!']
        base_response = BaseResponse(
            'Hello World!', content_type='text/html'
        )

        class SpecialResponse(Response):

            def foo(self):
                return 42

        # good enough for this simple application, but don't ever use that in
        # real world examples!
        fake_env = {}

        for orig_resp in wsgi_application, base_response:
            response = SpecialResponse.force_type(orig_resp, fake_env)
            self.assertEqual(response.__class__, SpecialResponse)
            self.assertEqual(response.foo(), 42)
            self.assertEqual(response.get_data(), b'Hello World!')
            self.assertEqual(response.content_type, 'text/html')

        # without env, no arbitrary conversion
        self.assertRaises(
            TypeError, SpecialResponse.force_type, wsgi_application
        )

    def test_etag_response_mixin(self):
        response = Response('Hello World')
        self.assertEqual(response.get_etag(), (None, None))
        response.add_etag()
        self.assertEqual(
            response.get_etag(), ('b10a8db164e0754105b7a99be72e3fe5', False)
        )
        self.assertFalse(response.cache_control)
        response.cache_control.must_revalidate = True
        response.cache_control.max_age = 60
        response.headers['Content-Length'] = len(response.get_data())
        self.assertIn(
            response.headers['Cache-Control'],
            ('must-revalidate, max-age=60', 'max-age=60, must-revalidate')
        )

        self.assertNotIn('date', response.headers)
        env = create_environ()
        env.update({
            'REQUEST_METHOD':       'GET',
            'HTTP_IF_NONE_MATCH':   response.get_etag()[0]
        })
        response.make_conditional(env)
        self.assertIn('date', response.headers)

        # after the thing is invoked by the server as wsgi application
        # (we're emulating this here), there must not be any entity
        # headers left and the status code would have to be 304
        resp = Response.from_app(response, env)
        self.assertEqual(resp.status_code, 304)
        self.assertNotIn('content-length', resp.headers)

        # make sure date is not overriden
        response = Response('Hello World')
        response.date = 1337
        d = response.date
        response.make_conditional(env)
        self.assertEqual(response.date, d)

        # make sure content length is only set if missing
        response = Response('Hello World')
        response.content_length = 999
        response.make_conditional(env)
        self.assertEqual(response.content_length, 999)

    def test_etag_response_mixin_freezing(self):
        class WithFreeze(ETagResponseMixin, BaseResponse):
            pass

        class WithoutFreeze(BaseResponse, ETagResponseMixin):
            pass

        response = WithFreeze('Hello World')
        response.freeze()
        self.assertEqual(
            response.get_etag(),
            (str(generate_etag(b'Hello World')), False)
        )
        response = WithoutFreeze('Hello World')
        response.freeze()
        self.assertEqual(response.get_etag(), (None, None))
        response = Response('Hello World')
        response.freeze()
        self.assertEqual(response.get_etag(), (None, None))

    def test_authenticate_mixin(self):
        resp = Response()
        resp.www_authenticate.type = 'basic'
        resp.www_authenticate.realm = 'Testing'
        self.assertEqual(
            resp.headers['WWW-Authenticate'], u'Basic realm="Testing"'
        )
        resp.www_authenticate.realm = None
        resp.www_authenticate.type = None
        self.assertNotIn('WWW-Authenticate', resp.headers)

    def test_authenticate_mixin_quoted_qop(self):
        # Example taken from https://github.com/mitsuhiko/werkzeug/issues/633
        resp = Response()
        resp.www_authenticate.set_digest(
            'REALM', 'NONCE', qop=("auth", "auth-int")
        )

        actual = set((resp.headers['WWW-Authenticate'] + ',').split())
        expected = set(
            ('Digest nonce="NONCE", realm="REALM", '
             'qop="auth, auth-int",').split()
        )
        self.assertEqual(actual, expected)

        resp.www_authenticate.set_digest('REALM', 'NONCE', qop=("auth",))

        actual = set((resp.headers['WWW-Authenticate'] + ',').split())
        expected = set(
            'Digest nonce="NONCE", realm="REALM", qop="auth",'.split()
        )
        self.assertEqual(actual, expected)

    def test_response_stream_mixin(self):
        response = Response()
        response.stream.write('Hello ')
        response.stream.write('World!')
        self.assertEqual(response.response, ['Hello ', 'World!'])
        self.assertEqual(response.get_data(), b'Hello World!')

    def test_common_response_descriptors_mixin(self):
        response = Response()
        response.mimetype = 'text/html'
        self.assertEqual(response.mimetype, 'text/html')
        self.assertEqual(response.content_type, 'text/html; charset=utf-8')
        self.assertEqual(response.mimetype_params, {'charset': 'utf-8'})
        response.mimetype_params['x-foo'] = 'yep'
        del response.mimetype_params['charset']
        self.assertEqual(response.content_type, 'text/html; x-foo=yep')

        now = datetime.utcnow().replace(microsecond=0)

        self.assertIsNone(response.content_length)
        response.content_length = '42'
        self.assertEqual(response.content_length, 42)

        for attr in 'date', 'age', 'expires':
            self.assertIsNone(getattr(response, attr))
            setattr(response, attr, now)
            self.assertEqual(getattr(response, attr), now)

        self.assertIsNone(response.retry_after)
        response.retry_after = now
        self.assertEqual(response.retry_after, now)

        self.assertFalse(response.vary)
        response.vary.add('Cookie')
        response.vary.add('Content-Language')
        self.assertTrue('cookie' in response.vary)
        self.assertEqual(response.vary.to_header(), 'Cookie, Content-Language')
        response.headers['Vary'] = 'Content-Encoding'
        self.assertEqual(response.vary.as_set(), set(['content-encoding']))

        response.allow.update(['GET', 'POST'])
        self.assertEqual(response.headers['Allow'], 'GET, POST')

        response.content_language.add('en-US')
        response.content_language.add('fr')
        self.assertEqual(response.headers['Content-Language'], 'en-US, fr')

    def test_response_streamed(self):
        r = Response()
        self.assertFalse(r.is_streamed)
        r = Response("Hello World")
        self.assertFalse(r.is_streamed)
        r = Response(["foo", "bar"])
        self.assertFalse(r.is_streamed)

        def gen():
            if 0:
                yield None
        r = Response(gen())
        self.assertTrue(r.is_streamed)

    def test_response_iter_wrapping(self):
        def uppercasing(iterator):
            for item in iterator:
                yield item.upper()

        def generator():
            yield 'foo'
            yield 'bar'
        req = Request.from_values()
        resp = Response(generator())
        del resp.headers['Content-Length']
        resp.response = uppercasing(resp.iter_encoded())
        actual_resp = Response.from_app(
            resp, req.environ, buffered=True
        )
        self.assertEqual(actual_resp.get_data(), b'FOOBAR')

    def test_response_freeze(self):
        def generate():
            yield "foo"
            yield "bar"
        resp = Response(generate())
        resp.freeze()
        self.assertEqual(resp.response, [b'foo', b'bar'])
        self.assertEqual(resp.headers['content-length'], '6')

    def test_urlfication(self):
        resp = Response()
        resp.headers['Location'] = u'http://üser:pässword@☃.net/påth'
        resp.headers['Content-Location'] = u'http://☃.net/'
        headers = resp.get_wsgi_headers(create_environ())
        self.assertEqual(
            headers['location'],
            'http://%C3%BCser:p%C3%A4ssword@xn--n3h.net/p%C3%A5th'
        )
        self.assertEqual(
            headers['content-location'],
            'http://xn--n3h.net/'
        )

    def test_new_response_iterator_behavior(self):
        req = Request.from_values()
        resp = Response(u'Hello Wörld!')

        def get_content_length(resp):
            headers = resp.get_wsgi_headers(req.environ)
            return headers.get('content-length', type=int)

        def generate_items():
            yield "Hello "
            yield u"Wörld!"

        # verktyg encodes when set to `data` now, which happens
        # if a string is passed to the response object.
        self.assertEqual(resp.response, [u'Hello Wörld!'.encode('utf-8')])
        self.assertEqual(resp.get_data(), u'Hello Wörld!'.encode('utf-8'))
        self.assertEqual(get_content_length(resp), 13)
        self.assertFalse(resp.is_streamed)
        self.assertTrue(resp.is_sequence)

        # try the same for manual assignment
        resp.set_data(u'Wörd')
        self.assertEqual(resp.response, [u'Wörd'.encode('utf-8')])
        self.assertEqual(resp.get_data(), u'Wörd'.encode('utf-8'))
        self.assertEqual(get_content_length(resp), 5)
        self.assertFalse(resp.is_streamed)
        self.assertTrue(resp.is_sequence)

        # automatic generator sequence conversion
        resp.response = generate_items()
        self.assertTrue(resp.is_streamed)
        self.assertFalse(resp.is_sequence)
        self.assertEqual(resp.get_data(), u'Hello Wörld!'.encode('utf-8'))
        self.assertEqual(resp.response, [b'Hello ', u'Wörld!'.encode('utf-8')])
        self.assertFalse(resp.is_streamed)
        self.assertTrue(resp.is_sequence)

        # automatic generator sequence conversion
        resp.response = generate_items()
        resp.implicit_sequence_conversion = False
        self.assertTrue(resp.is_streamed)
        self.assertFalse(resp.is_sequence)
        self.assertRaises(RuntimeError, lambda: resp.get_data())
        resp.make_sequence()
        self.assertEqual(resp.get_data(), u'Hello Wörld!'.encode('utf-8'))
        self.assertEqual(resp.response, [b'Hello ', u'Wörld!'.encode('utf-8')])
        self.assertFalse(resp.is_streamed)
        self.assertTrue(resp.is_sequence)

        # stream makes it a list no matter how the conversion is set
        for val in True, False:
            resp.implicit_sequence_conversion = val
            resp.response = ("foo", "bar")
            self.assertTrue(resp.is_sequence)
            resp.stream.write('baz')
            self.assertEqual(resp.response, ['foo', 'bar', 'baz'])

    def test_response_headers_passthrough(self):
        headers = Headers()
        resp = Response(headers=headers)
        self.assertIs(resp.headers, headers)

    def test_response_304_no_content_length(self):
        resp = Response('Test', status=304)
        env = create_environ()
        self.assertNotIn('content-length', resp.get_wsgi_headers(env))

    def test_ranges(self):
        # basic range stuff
        req = Request.from_values()
        self.assertIsNone(req.range)
        req = Request.from_values(headers={'Range': 'bytes=0-499'})
        self.assertEqual(req.range.ranges, [(0, 500)])

        resp = Response()
        resp.content_range = req.range.make_content_range(1000)
        self.assertEqual(resp.content_range.units, 'bytes')
        self.assertEqual(resp.content_range.start, 0)
        self.assertEqual(resp.content_range.stop, 500)
        self.assertEqual(resp.content_range.length, 1000)
        self.assertEqual(resp.headers['Content-Range'], 'bytes 0-499/1000')

        resp.content_range.unset()
        self.assertNotIn('Content-Range', resp.headers)

        resp.headers['Content-Range'] = 'bytes 0-499/1000'
        self.assertEqual(resp.content_range.units, 'bytes')
        self.assertEqual(resp.content_range.start, 0)
        self.assertEqual(resp.content_range.stop, 500)
        self.assertEqual(resp.content_range.length, 1000)

    def test_auto_content_length(self):
        resp = Response('Hello World!')
        self.assertEqual(resp.content_length, 12)

        resp = Response(['Hello World!'])
        self.assertIsNone(resp.content_length)
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '12')

    def test_stream_content_length(self):
        resp = Response()
        resp.stream.writelines(['foo', 'bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

        resp = Response()
        resp.make_conditional({'REQUEST_METHOD': 'GET'})
        resp.stream.writelines(['foo', 'bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

        resp = Response('foo')
        resp.stream.writelines(['bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

    def test_disabled_auto_content_length(self):
        class MyResponse(Response):
            automatically_set_content_length = False
        resp = MyResponse('Hello World!')
        self.assertIsNone(resp.content_length)

        resp = MyResponse(['Hello World!'])
        self.assertIsNone(resp.content_length)
        self.assertNotIn('Content-Length', resp.get_wsgi_headers({}))

        resp = MyResponse()
        resp.make_conditional({
            'REQUEST_METHOD': 'GET'
        })
        self.assertIsNone(resp.content_length)
        self.assertNotIn('Content-Length', resp.get_wsgi_headers({}))

    def test_location_header_autocorrect(self):
        env = create_environ()

        class MyResponse(Response):
            autocorrect_location_header = False
        resp = MyResponse('Hello World!')
        resp.headers['Location'] = '/test'
        self.assertEqual(resp.get_wsgi_headers(env)['Location'], '/test')

        resp = Response('Hello World!')
        resp.headers['Location'] = '/test'
        self.assertEqual(
            resp.get_wsgi_headers(env)['Location'], 'http://localhost/test'
        )


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ResponsesTestCase))
    return suite
