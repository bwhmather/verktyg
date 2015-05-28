# -*- coding: utf-8 -*-
"""
    tests.wrappers
    ~~~~~~~~~~~~~~

    Tests for the response and request objects.

    :copyright: (c) 2014 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import unittest

import pickle
from io import BytesIO
from datetime import datetime

from werkzeug.exceptions import SecurityError
from werkzeug.wsgi import LimitedStream
from werkzeug.datastructures import MultiDict, ImmutableOrderedMultiDict, \
    ImmutableList, ImmutableTypeConversionDict, CharsetAccept, \
    MIMEAccept, LanguageAccept, Accept, CombinedMultiDict
from werkzeug.test import Client, create_environ, run_wsgi_app

from verktyg import wrappers


class RequestTestResponse(wrappers.BaseResponse):

    """Subclass of the normal response class we use to test response
    and base classes.  Has some methods to test if things in the
    response match.
    """

    def __init__(self, response, status, headers):
        wrappers.BaseResponse.__init__(self, response, status, headers)
        self.body_data = pickle.loads(self.get_data())

    def __getitem__(self, key):
        return self.body_data[key]


def request_demo_app(environ, start_response):
    request = wrappers.BaseRequest(environ)
    assert 'verktyg.request' in environ
    start_response('200 OK', [('Content-Type', 'text/plain')])
    return [pickle.dumps({
        'args':             request.args,
        'args_as_list':     list(request.args.lists()),
        'form':             request.form,
        'form_as_list':     list(request.form.lists()),
        'environ':          prepare_environ_pickle(request.environ),
        'data':             request.get_data()
    })]


def prepare_environ_pickle(environ):
    result = {}
    for key, value in environ.items():
        try:
            pickle.dumps((key, value))
        except Exception:
            continue
        result[key] = value
    return result


class WrappersTestCase(unittest.TestCase):
    def assert_environ(self, environ, method):
        self.assertEqual(environ['REQUEST_METHOD'], method)
        self.assertEqual(environ['PATH_INFO'], '/')
        self.assertEqual(environ['SCRIPT_NAME'], '')
        self.assertEqual(environ['SERVER_NAME'], 'localhost')
        self.assertEqual(environ['wsgi.version'], (1, 0))
        self.assertEqual(environ['wsgi.url_scheme'], 'http')

    def test_base_request(self):
        client = Client(request_demo_app, RequestTestResponse)

        # get requests
        response = client.get('/?foo=bar&foo=hehe')
        self.assertEqual(
            response['args'], MultiDict([('foo', u'bar'), ('foo', u'hehe')])
        )
        self.assertEqual(
            response['args_as_list'], [('foo', [u'bar', u'hehe'])]
        )
        self.assertEqual(response['form'], MultiDict())
        self.assertEqual(response['form_as_list'], [])
        self.assertEqual(response['data'], b'')
        self.assert_environ(response['environ'], 'GET')

        # post requests with form data
        response = client.post(
            '/?blub=blah', data='foo=blub+hehe&blah=42',
            content_type='application/x-www-form-urlencoded'
        )
        self.assertEqual(response['args'], MultiDict([('blub', u'blah')]))
        self.assertEqual(response['args_as_list'], [('blub', [u'blah'])])
        self.assertEqual(
            response['form'], MultiDict([
                ('foo', u'blub hehe'), ('blah', u'42'),
            ])
        )
        self.assertEqual(response['data'], b'')
        self.assert_environ(response['environ'], 'POST')

        # patch requests with form data
        response = client.patch(
            '/?blub=blah', data='foo=blub+hehe&blah=42',
            content_type='application/x-www-form-urlencoded'
        )
        self.assertEqual(response['args'], MultiDict([('blub', u'blah')]))
        self.assertEqual(response['args_as_list'], [('blub', [u'blah'])])
        self.assertEqual(
            response['form'], MultiDict([
                ('foo', u'blub hehe'), ('blah', u'42'),
            ])
        )
        self.assertEqual(response['data'], b'')
        self.assert_environ(response['environ'], 'PATCH')

        # post requests with json data
        json = b'{"foo": "bar", "blub": "blah"}'
        response = client.post(
            '/?a=b', data=json, content_type='application/json'
        )
        self.assertEqual(response['data'], json)
        self.assertEqual(response['args'], MultiDict([('a', u'b')]))
        self.assertEqual(response['form'], MultiDict())

    def test_query_string_is_bytes(self):
        req = wrappers.Request.from_values(u'/?foo=%2f')
        self.assertEqual(req.query_string, b'foo=%2f')

    def test_request_repr(self):
        req = wrappers.Request.from_values('/foobar')
        self.assertEqual(
            "<Request 'http://localhost/foobar' [GET]>", repr(req)
        )
        # test with non-ascii characters
        req = wrappers.Request.from_values('/привет')
        self.assertEqual(
            "<Request 'http://localhost/привет' [GET]>", repr(req)
        )
        # test with unicode type for python 2
        req = wrappers.Request.from_values(u'/привет')
        self.assertEqual(
            "<Request 'http://localhost/привет' [GET]>", repr(req)
        )

    def test_access_route(self):
        req = wrappers.Request.from_values(headers={
            'X-Forwarded-For': '192.168.1.2, 192.168.1.1'
        })
        req.environ['REMOTE_ADDR'] = '192.168.1.3'
        self.assertEqual(req.access_route, ['192.168.1.2', '192.168.1.1'])
        self.assertEqual(req.remote_addr, '192.168.1.3')

        req = wrappers.Request.from_values()
        req.environ['REMOTE_ADDR'] = '192.168.1.3'
        self.assertEqual(list(req.access_route), ['192.168.1.3'])

    def test_url_request_descriptors(self):
        req = wrappers.Request.from_values(
            '/bar?foo=baz', 'http://example.com/test'
        )
        self.assertEqual(req.path, u'/bar')
        self.assertEqual(req.full_path, u'/bar?foo=baz')
        self.assertEqual(req.script_root, u'/test')
        self.assertEqual(req.url, u'http://example.com/test/bar?foo=baz')
        self.assertEqual(req.base_url, u'http://example.com/test/bar')
        self.assertEqual(req.url_root, u'http://example.com/test/')
        self.assertEqual(req.host_url, u'http://example.com/')
        self.assertEqual(req.host, 'example.com')
        self.assertEqual(req.scheme, 'http')

        req = wrappers.Request.from_values(
            '/bar?foo=baz', 'https://example.com/test'
        )
        self.assertEqual(req.scheme, 'https')

    def test_url_request_descriptors_query_quoting(self):
        next = 'http%3A%2F%2Fwww.example.com%2F%3Fnext%3D%2F'
        req = wrappers.Request.from_values(
            '/bar?next=' + next, 'http://example.com/'
        )
        self.assertEqual(req.path, u'/bar')
        self.assertEqual(req.full_path, u'/bar?next=' + next)
        self.assertEqual(req.url, u'http://example.com/bar?next=' + next)

    def test_url_request_descriptors_hosts(self):
        req = wrappers.Request.from_values(
            '/bar?foo=baz', 'http://example.com/test'
        )
        req.trusted_hosts = ['example.com']
        self.assertEqual(req.path, u'/bar')
        self.assertEqual(req.full_path, u'/bar?foo=baz')
        self.assertEqual(req.script_root, u'/test')
        self.assertEqual(req.url, u'http://example.com/test/bar?foo=baz')
        self.assertEqual(req.base_url, u'http://example.com/test/bar')
        self.assertEqual(req.url_root, u'http://example.com/test/')
        self.assertEqual(req.host_url, u'http://example.com/')
        self.assertEqual(req.host, 'example.com')
        self.assertEqual(req.scheme, 'http')

        req = wrappers.Request.from_values(
            '/bar?foo=baz', 'https://example.com/test'
        )
        self.assertEqual(req.scheme, 'https')

        req = wrappers.Request.from_values(
            '/bar?foo=baz', 'http://example.com/test'
        )
        req.trusted_hosts = ['example.org']
        self.assertRaises(SecurityError, lambda: req.url)
        self.assertRaises(SecurityError, lambda: req.base_url)
        self.assertRaises(SecurityError, lambda: req.url_root)
        self.assertRaises(SecurityError, lambda: req.host_url)
        self.assertRaises(SecurityError, lambda: req.host)

    def test_authorization_mixin(self):
        request = wrappers.Request.from_values(headers={
            'Authorization': 'Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=='
        })
        a = request.authorization
        self.assertEqual(a.type, 'basic')
        self.assertEqual(a.username, 'Aladdin')
        self.assertEqual(a.password, 'open sesame')

    def test_stream_only_mixing(self):
        request = wrappers.PlainRequest.from_values(
            data=b'foo=blub+hehe',
            content_type='application/x-www-form-urlencoded'
        )
        self.assertEqual(list(request.files.items()), [])
        self.assertEqual(list(request.form.items()), [])
        self.assertRaises(AttributeError, lambda: request.data)
        self.assertEqual(request.stream.read(), b'foo=blub+hehe')

    def test_base_response(self):
        # unicode
        response = wrappers.BaseResponse(u'öäü')
        self.assertEqual(response.get_data(), u'öäü'.encode('utf-8'))

        # writing
        response = wrappers.Response('foo')
        response.stream.write('bar')
        self.assertEqual(response.get_data(), b'foobar')

        # set cookie
        response = wrappers.BaseResponse()
        response.set_cookie('foo', 'bar', 60, 0, '/blub', 'example.org')
        self.assertEqual(response.headers.to_wsgi_list(), [
            ('Content-Type', 'text/plain; charset=utf-8'),
            ('Set-Cookie', 'foo=bar; Domain=example.org; Expires=Thu, '
             '01-Jan-1970 00:00:00 GMT; Max-Age=60; Path=/blub')
        ])

        # delete cookie
        response = wrappers.BaseResponse()
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
        response = wrappers.BaseResponse(Iterable())
        response.call_on_close(lambda: closed.append(True))
        app_iter, status, headers = run_wsgi_app(response,
                                                 create_environ(),
                                                 buffered=True)
        self.assertEqual(status, '200 OK')
        self.assertEqual(''.join(app_iter), '')
        self.assertEqual(len(closed), 2)

        # with statement
        del closed[:]
        response = wrappers.BaseResponse(Iterable())
        with response:
            pass
        self.assertEqual(len(closed), 1)

    def test_response_status_codes(self):
        response = wrappers.BaseResponse()
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
        base_response = wrappers.BaseResponse(
            'Hello World!', content_type='text/html'
        )

        class SpecialResponse(wrappers.Response):

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

    def test_accept_mixin(self):
        request = wrappers.Request({
            'HTTP_ACCEPT': 'text/xml,application/xml,application/xhtml+xml,'
                           'text/html;q=0.9,text/plain;q=0.8,image/png,'
                           '*/*;q=0.5',
            'HTTP_ACCEPT_CHARSET': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
            'HTTP_ACCEPT_ENCODING': 'gzip,deflate',
            'HTTP_ACCEPT_LANGUAGE': 'en-us,en;q=0.5'
        })
        self.assertEqual(request.accept_mimetypes, MIMEAccept([
            ('text/xml', 1), ('image/png', 1), ('application/xml', 1),
            ('application/xhtml+xml', 1), ('text/html', 0.9),
            ('text/plain', 0.8), ('*/*', 0.5)
        ]))
        self.assertEqual(request.accept_charsets, CharsetAccept([
            ('ISO-8859-1', 1), ('utf-8', 0.7), ('*', 0.7)
        ]))
        self.assertEqual(request.accept_encodings, Accept([
            ('gzip', 1), ('deflate', 1)]))
        self.assertEqual(request.accept_languages, LanguageAccept([
            ('en-us', 1), ('en', 0.5)]))

        request = wrappers.Request({'HTTP_ACCEPT': ''})
        self.assertEqual(request.accept_mimetypes, MIMEAccept())

    def test_etag_request_mixin(self):
        request = wrappers.Request({
            'HTTP_CACHE_CONTROL':       'no-store, no-cache',
            'HTTP_IF_MATCH':            'w/"foo", bar, "baz"',
            'HTTP_IF_NONE_MATCH':       'w/"foo", bar, "baz"',
            'HTTP_IF_MODIFIED_SINCE':   'Tue, 22 Jan 2008 11:18:44 GMT',
            'HTTP_IF_UNMODIFIED_SINCE': 'Tue, 22 Jan 2008 11:18:44 GMT'
        })
        self.assertTrue(request.cache_control.no_store)
        self.assertTrue(request.cache_control.no_cache)

        for etags in request.if_match, request.if_none_match:
            self.assertTrue(etags('bar'))
            self.assertTrue(etags.contains_raw('w/"foo"'))
            self.assertTrue(etags.contains_weak('foo'))
            self.assertFalse(etags.contains('foo'))

        self.assertEqual(
            request.if_modified_since, datetime(2008, 1, 22, 11, 18, 44)
        )
        self.assertEqual(
            request.if_unmodified_since, datetime(2008, 1, 22, 11, 18, 44)
        )

    def test_user_agent_mixin(self):
        user_agents = [
            ('Mozilla/5.0 (Macintosh; U; Intel Mac OS X; en-US; rv:1.8.1.11) '
             'Gecko/20071127 Firefox/2.0.0.11', 'firefox', 'macos', '2.0.0.11',
             'en-US'),
            ('Mozilla/4.0 (compatible; MSIE 6.0; Windows NT 5.1; de-DE) '
             'Opera 8.54',
             'opera', 'windows', '8.54', 'de-DE'),
            ('Mozilla/5.0 (iPhone; U; CPU like Mac OS X; en) AppleWebKit/420 '
             '(KHTML, like Gecko) Version/3.0 Mobile/1A543a Safari/419.3',
             'safari', 'iphone', '3.0', 'en'),
            ('Bot Googlebot/2.1 (http://www.googlebot.com/bot.html)',
             'google', None, '2.1', None),
            ('Mozilla/5.0 (X11; CrOS armv7l 3701.81.0) AppleWebKit/537.31 '
             '(KHTML, like Gecko) Chrome/26.0.1410.57 Safari/537.31',
             'chrome', 'chromeos', '26.0.1410.57', None),
            ('Mozilla/5.0 (Windows NT 6.3; Trident/7.0; .NET4.0E; rv:11.0) '
             'like Gecko',
             'msie', 'windows', '11.0', None),
            ('Mozilla/5.0 (SymbianOS/9.3; Series60/3.2 NokiaE5-00/101.003; '
             'Profile/MIDP-2.1 Configuration/CLDC-1.1 ) AppleWebKit/533.4 '
             '(KHTML, like Gecko) NokiaBrowser/7.3.1.35 '
             'Mobile Safari/533.4 3gpp-gba',
             'safari', 'symbian', '533.4', None)
        ]
        for ua, browser, platform, version, lang in user_agents:
            request = wrappers.Request({'HTTP_USER_AGENT': ua})
            self.assertEqual(request.user_agent.browser, browser)
            self.assertEqual(request.user_agent.platform, platform)
            self.assertEqual(request.user_agent.version, version)
            self.assertEqual(request.user_agent.language, lang)
            self.assertTrue(bool(request.user_agent))
            self.assertEqual(request.user_agent.to_header(), ua)
            self.assertEqual(str(request.user_agent), ua)

        request = wrappers.Request({'HTTP_USER_AGENT': 'foo'})
        self.assertFalse(request.user_agent)

    def test_stream_wrapping(self):
        class LowercasingStream(object):

            def __init__(self, stream):
                self._stream = stream

            def read(self, size=-1):
                return self._stream.read(size).lower()

            def readline(self, size=-1):
                return self._stream.readline(size).lower()

        data = b'foo=Hello+World'
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        req.stream = LowercasingStream(req.stream)
        self.assertEqual(req.form['foo'], 'hello world')

    def test_data_descriptor_triggers_parsing(self):
        data = b'foo=Hello+World'
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')

        self.assertEqual(req.data, b'')
        self.assertEqual(req.form['foo'], u'Hello World')

    def test_get_data_method_parsing_caching_behavior(self):
        data = b'foo=Hello+World'
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')

        # get_data() caches, so form stays available
        self.assertEqual(req.get_data(), data)
        self.assertEqual(req.form['foo'], u'Hello World')
        self.assertEqual(req.get_data(), data)

        # here we access the form data first, caching is bypassed
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.form['foo'], u'Hello World')
        self.assertEqual(req.get_data(), b'')

        # Another case is uncached get data which trashes everything
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.get_data(cache=False), data)
        self.assertEqual(req.get_data(cache=False), b'')
        self.assertEqual(req.form, {})

        # Or we can implicitly start the form parser which is similar to
        # the old .data behavior
        req = wrappers.Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.get_data(parse_form_data=True), b'')
        self.assertEqual(req.form['foo'], u'Hello World')

    def test_etag_response_mixin(self):
        response = wrappers.Response('Hello World')
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
        resp = wrappers.Response.from_app(response, env)
        self.assertEqual(resp.status_code, 304)
        self.assertNotIn('content-length', resp.headers)

        # make sure date is not overriden
        response = wrappers.Response('Hello World')
        response.date = 1337
        d = response.date
        response.make_conditional(env)
        self.assertEqual(response.date, d)

        # make sure content length is only set if missing
        response = wrappers.Response('Hello World')
        response.content_length = 999
        response.make_conditional(env)
        self.assertEqual(response.content_length, 999)

    def test_etag_response_mixin_freezing(self):
        class WithFreeze(wrappers.ETagResponseMixin, wrappers.BaseResponse):
            pass

        class WithoutFreeze(wrappers.BaseResponse, wrappers.ETagResponseMixin):
            pass

        response = WithFreeze('Hello World')
        response.freeze()
        self.assertEqual(
            response.get_etag(),
            (str(wrappers.generate_etag(b'Hello World')), False)
        )
        response = WithoutFreeze('Hello World')
        response.freeze()
        self.assertEqual(response.get_etag(), (None, None))
        response = wrappers.Response('Hello World')
        response.freeze()
        self.assertEqual(response.get_etag(), (None, None))

    def test_authenticate_mixin(self):
        resp = wrappers.Response()
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
        resp = wrappers.Response()
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
        response = wrappers.Response()
        response.stream.write('Hello ')
        response.stream.write('World!')
        self.assertEqual(response.response, ['Hello ', 'World!'])
        self.assertEqual(response.get_data(), b'Hello World!')

    def test_common_response_descriptors_mixin(self):
        response = wrappers.Response()
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

    def test_common_request_descriptors_mixin(self):
        request = wrappers.Request.from_values(
            content_type='text/html; charset=utf-8',
            content_length='23',
            headers={
                'Referer':          'http://www.example.com/',
                'Date':             'Sat, 28 Feb 2009 19:04:35 GMT',
                'Max-Forwards':     '10',
                'Pragma':           'no-cache',
                'Content-Encoding': 'gzip',
                'Content-MD5':      '9a3bc6dbc47a70db25b84c6e5867a072'
            }
        )

        self.assertEqual(request.content_type, 'text/html; charset=utf-8')
        self.assertEqual(request.mimetype, 'text/html')
        self.assertEqual(request.mimetype_params, {'charset': 'utf-8'})
        self.assertEqual(request.content_length, 23)
        self.assertEqual(request.referrer, 'http://www.example.com/')
        self.assertEqual(request.date, datetime(2009, 2, 28, 19, 4, 35))
        self.assertEqual(request.max_forwards, 10)
        self.assertTrue('no-cache' in request.pragma)
        self.assertEqual(request.content_encoding, 'gzip')
        self.assertEqual(
            request.content_md5, '9a3bc6dbc47a70db25b84c6e5867a072'
        )

    def test_request_mimetype_always_lowercase(self):
        request = wrappers.Request.from_values(content_type='APPLICATION/JSON')
        self.assertEqual(request.mimetype, 'application/json')

    def test_shallow_mode(self):
        request = wrappers.Request({'QUERY_STRING': 'foo=bar'}, shallow=True)
        self.assertEqual(request.args['foo'], 'bar')
        self.assertRaises(RuntimeError, lambda: request.form['foo'])

    def test_form_parsing_failed(self):
        data = (
            b'--blah\r\n'
        )
        data = wrappers.Request.from_values(
            input_stream=BytesIO(data),
            content_length=len(data),
            content_type='multipart/form-data; boundary=foo',
            method='POST'
        )
        self.assertFalse(data.files)
        self.assertFalse(data.form)

    def test_file_closing(self):
        data = (
            b'--foo\r\n'
            b'Content-Disposition: form-data; name="foo"; '
            b'filename="foo.txt"\r\n'
            b'Content-Type: text/plain; charset=utf-8\r\n\r\n'
            b'file contents, just the contents\r\n'
            b'--foo--'
        )
        req = wrappers.Request.from_values(
            input_stream=BytesIO(data),
            content_length=len(data),
            content_type='multipart/form-data; boundary=foo',
            method='POST'
        )
        foo = req.files['foo']
        self.assertEqual(foo.mimetype, 'text/plain')
        self.assertEqual(foo.filename, 'foo.txt')

        self.assertFalse(foo.closed)
        req.close()
        self.assertTrue(foo.closed)

    def test_file_closing_with(self):
        data = (
            b'--foo\r\n'
            b'Content-Disposition: form-data; name="foo"; '
            b'filename="foo.txt"\r\n'
            b'Content-Type: text/plain; charset=utf-8\r\n\r\n'
            b'file contents, just the contents\r\n'
            b'--foo--'
        )
        req = wrappers.Request.from_values(
            input_stream=BytesIO(data),
            content_length=len(data),
            content_type='multipart/form-data; boundary=foo',
            method='POST'
        )
        with req:
            foo = req.files['foo']
            self.assertEqual(foo.mimetype, 'text/plain')
            self.assertEqual(foo.filename, 'foo.txt')

        self.assertTrue(foo.closed)

    def test_url_charset_reflection(self):
        req = wrappers.Request.from_values()
        req.charset = 'utf-7'
        self.assertEqual(req.url_charset, 'utf-7')

    def test_response_streamed(self):
        r = wrappers.Response()
        self.assertFalse(r.is_streamed)
        r = wrappers.Response("Hello World")
        self.assertFalse(r.is_streamed)
        r = wrappers.Response(["foo", "bar"])
        self.assertFalse(r.is_streamed)

        def gen():
            if 0:
                yield None
        r = wrappers.Response(gen())
        self.assertTrue(r.is_streamed)

    def test_response_iter_wrapping(self):
        def uppercasing(iterator):
            for item in iterator:
                yield item.upper()

        def generator():
            yield 'foo'
            yield 'bar'
        req = wrappers.Request.from_values()
        resp = wrappers.Response(generator())
        del resp.headers['Content-Length']
        resp.response = uppercasing(resp.iter_encoded())
        actual_resp = wrappers.Response.from_app(
            resp, req.environ, buffered=True
        )
        self.assertEqual(actual_resp.get_data(), b'FOOBAR')

    def test_response_freeze(self):
        def generate():
            yield "foo"
            yield "bar"
        resp = wrappers.Response(generate())
        resp.freeze()
        self.assertEqual(resp.response, [b'foo', b'bar'])
        self.assertEqual(resp.headers['content-length'], '6')

    def test_other_method_payload(self):
        data = b'Hello World'
        req = wrappers.Request.from_values(
            input_stream=BytesIO(data), method='WHAT_THE_FUCK',
            content_length=len(data), content_type='text/plain'
        )
        self.assertEqual(req.get_data(), data)
        self.assertTrue(isinstance(req.stream, LimitedStream))

    def test_urlfication(self):
        resp = wrappers.Response()
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
        req = wrappers.Request.from_values()
        resp = wrappers.Response(u'Hello Wörld!')

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

    def test_form_data_ordering(self):
        class MyRequest(wrappers.Request):
            parameter_storage_class = ImmutableOrderedMultiDict

        req = MyRequest.from_values('/?foo=1&bar=0&foo=3')
        self.assertEqual(list(req.args), ['foo', 'bar'])
        self.assertEqual(list(req.args.items(multi=True)), [
            ('foo', '1'),
            ('bar', '0'),
            ('foo', '3')
        ])
        self.assertIsInstance(req.args, ImmutableOrderedMultiDict)
        self.assertIsInstance(req.values, CombinedMultiDict)
        self.assertEqual(req.values['foo'], '1')
        self.assertEqual(req.values.getlist('foo'), ['1', '3'])

    def test_storage_classes(self):
        class MyRequest(wrappers.Request):
            dict_storage_class = dict
            list_storage_class = list
            parameter_storage_class = dict
        req = MyRequest.from_values('/?foo=baz', headers={
            'Cookie':   'foo=bar'
        })
        self.assertIs(type(req.cookies), dict)
        self.assertEqual(req.cookies, {'foo': 'bar'})
        self.assertIs(type(req.access_route), list)

        self.assertIs(type(req.args), dict)
        self.assertIs(type(req.values), CombinedMultiDict)
        self.assertEqual(req.values['foo'], u'baz')

        req = wrappers.Request.from_values(headers={
            'Cookie':   'foo=bar'
        })
        self.assertIs(type(req.cookies), ImmutableTypeConversionDict)
        self.assertEqual(req.cookies, {'foo': 'bar'})
        self.assertIs(type(req.access_route), ImmutableList)

        MyRequest.list_storage_class = tuple
        req = MyRequest.from_values()
        self.assertIs(type(req.access_route), tuple)

    def test_response_headers_passthrough(self):
        headers = wrappers.Headers()
        resp = wrappers.Response(headers=headers)
        self.assertIs(resp.headers, headers)

    def test_response_304_no_content_length(self):
        resp = wrappers.Response('Test', status=304)
        env = create_environ()
        self.assertNotIn('content-length', resp.get_wsgi_headers(env))

    def test_ranges(self):
        # basic range stuff
        req = wrappers.Request.from_values()
        self.assertIsNone(req.range)
        req = wrappers.Request.from_values(headers={'Range': 'bytes=0-499'})
        self.assertEqual(req.range.ranges, [(0, 500)])

        resp = wrappers.Response()
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
        resp = wrappers.Response('Hello World!')
        self.assertEqual(resp.content_length, 12)

        resp = wrappers.Response(['Hello World!'])
        self.assertIsNone(resp.content_length)
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '12')

    def test_stream_content_length(self):
        resp = wrappers.Response()
        resp.stream.writelines(['foo', 'bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

        resp = wrappers.Response()
        resp.make_conditional({'REQUEST_METHOD': 'GET'})
        resp.stream.writelines(['foo', 'bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

        resp = wrappers.Response('foo')
        resp.stream.writelines(['bar', 'baz'])
        self.assertEqual(resp.get_wsgi_headers({})['Content-Length'], '9')

    def test_disabled_auto_content_length(self):
        class MyResponse(wrappers.Response):
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

        class MyResponse(wrappers.Response):
            autocorrect_location_header = False
        resp = MyResponse('Hello World!')
        resp.headers['Location'] = '/test'
        self.assertEqual(resp.get_wsgi_headers(env)['Location'], '/test')

        resp = wrappers.Response('Hello World!')
        resp.headers['Location'] = '/test'
        self.assertEqual(
            resp.get_wsgi_headers(env)['Location'], 'http://localhost/test'
        )

    def test_modified_url_encoding(self):
        class ModifiedRequest(wrappers.Request):
            url_charset = 'euc-kr'

        req = ModifiedRequest.from_values(u'/?foo=정상처리'.encode('euc-kr'))
        self.assertEqual(req.args['foo'], u'정상처리')

    def test_request_method_case_sensitivity(self):
        req = wrappers.Request({'REQUEST_METHOD': 'get'})
        self.assertEqual(req.method, 'GET')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(WrappersTestCase))
    return suite
