"""
    tests.requests
    ~~~~~~~~~~~~~~

    Tests for request objects.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

import pickle
from io import BytesIO
from datetime import datetime

from verktyg.datastructures import (
    MultiDict, ImmutableOrderedMultiDict, ImmutableList,
    ImmutableTypeConversionDict, CombinedMultiDict,
)
from verktyg.test import Client
from verktyg.wsgi import LimitedStream
from verktyg.exceptions import SecurityError
from verktyg.requests import BaseRequest, Request, PlainRequest
from verktyg.responses import BaseResponse


class RequestTestResponse(BaseResponse):

    """Subclass of the normal response class we use to test response
    and base classes.  Has some methods to test if things in the
    response match.
    """

    def __init__(self, response, status, headers):
        BaseResponse.__init__(self, response, status, headers)
        self.body_data = pickle.loads(self.get_data())

    def __getitem__(self, key):
        return self.body_data[key]


def request_demo_app(environ, start_response):
    request = BaseRequest(environ)
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


class RequestsTestCase(unittest.TestCase):
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
        req = Request.from_values(u'/?foo=%2f')
        self.assertEqual(req.query_string, b'foo=%2f')

    def test_request_repr(self):
        req = Request.from_values('/foobar')
        self.assertEqual(
            "<Request 'http://localhost/foobar' [GET]>", repr(req)
        )
        # test with non-ascii characters
        req = Request.from_values('/привет')
        self.assertEqual(
            "<Request 'http://localhost/привет' [GET]>", repr(req)
        )
        # test with unicode type for python 2
        req = Request.from_values(u'/привет')
        self.assertEqual(
            "<Request 'http://localhost/привет' [GET]>", repr(req)
        )

    def test_access_route(self):
        req = Request.from_values(headers={
            'X-Forwarded-For': '192.168.1.2, 192.168.1.1'
        })
        req.environ['REMOTE_ADDR'] = '192.168.1.3'
        self.assertEqual(req.access_route, ['192.168.1.2', '192.168.1.1'])
        self.assertEqual(req.remote_addr, '192.168.1.3')

        req = Request.from_values()
        req.environ['REMOTE_ADDR'] = '192.168.1.3'
        self.assertEqual(list(req.access_route), ['192.168.1.3'])

    def test_url_request_descriptors(self):
        req = Request.from_values(
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

        req = Request.from_values(
            '/bar?foo=baz', 'https://example.com/test'
        )
        self.assertEqual(req.scheme, 'https')

    def test_url_request_descriptors_query_quoting(self):
        next = 'http%3A%2F%2Fwww.example.com%2F%3Fnext%3D%2F'
        req = Request.from_values(
            '/bar?next=' + next, 'http://example.com/'
        )
        self.assertEqual(req.path, u'/bar')
        self.assertEqual(req.full_path, u'/bar?next=' + next)
        self.assertEqual(req.url, u'http://example.com/bar?next=' + next)

    def test_url_request_descriptors_hosts(self):
        req = Request.from_values(
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

        req = Request.from_values(
            '/bar?foo=baz', 'https://example.com/test'
        )
        self.assertEqual(req.scheme, 'https')

        req = Request.from_values(
            '/bar?foo=baz', 'http://example.com/test'
        )
        req.trusted_hosts = ['example.org']
        self.assertRaises(SecurityError, lambda: req.url)
        self.assertRaises(SecurityError, lambda: req.base_url)
        self.assertRaises(SecurityError, lambda: req.url_root)
        self.assertRaises(SecurityError, lambda: req.host_url)
        self.assertRaises(SecurityError, lambda: req.host)

    def test_authorization_mixin(self):
        request = Request.from_values(headers={
            'Authorization': 'Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=='
        })
        a = request.authorization
        self.assertEqual(a.type, 'basic')
        self.assertEqual(a.username, 'Aladdin')
        self.assertEqual(a.password, 'open sesame')

    def test_stream_only_mixing(self):
        request = PlainRequest.from_values(
            data=b'foo=blub+hehe',
            content_type='application/x-www-form-urlencoded'
        )
        self.assertEqual(list(request.files.items()), [])
        self.assertEqual(list(request.form.items()), [])
        self.assertEqual(request.stream.read(), b'foo=blub+hehe')

    def test_etag_request_mixin(self):
        request = Request({
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
            # ('Mozilla/5.0 (iPhone; U; CPU like Mac OS X; en) AppleWebKit/420'
            # ' (KHTML, like Gecko) Version/3.0 Mobile/1A543a Safari/419.3',
            # 'safari', 'iphone', '3.0', 'en'),
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
            request = Request({'HTTP_USER_AGENT': ua})
            self.assertEqual(request.user_agent.browser, browser)
            self.assertEqual(request.user_agent.platform, platform)
            self.assertEqual(request.user_agent.version, version)
            self.assertEqual(request.user_agent.language, lang)
            self.assertTrue(bool(request.user_agent))
            self.assertEqual(request.user_agent.to_header(), ua)
            self.assertEqual(str(request.user_agent), ua)

        request = Request({'HTTP_USER_AGENT': 'foo'})
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
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        req.stream = LowercasingStream(req.stream)
        self.assertEqual(req.form['foo'], 'hello world')

    def test_data_descriptor_triggers_parsing(self):
        data = b'foo=Hello+World'
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')

        self.assertEqual(req.get_data(parse_form_data=True), b'')
        self.assertEqual(req.form['foo'], u'Hello World')

    def test_get_data_method_parsing_caching_behavior(self):
        data = b'foo=Hello+World'
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')

        # get_data() caches, so form stays available
        self.assertEqual(req.get_data(), data)
        self.assertEqual(req.form['foo'], u'Hello World')
        self.assertEqual(req.get_data(), data)

        # here we access the form data first, caching is bypassed
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.form['foo'], u'Hello World')
        self.assertEqual(req.get_data(), b'')

        # Another case is uncached get data which trashes everything
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.get_data(cache=False), data)
        self.assertEqual(req.get_data(cache=False), b'')
        self.assertEqual(req.form, {})

        # Or we can implicitly start the form parser which is similar to
        # the old .data behavior
        req = Request.from_values(
            '/', method='POST', data=data,
            content_type='application/x-www-form-urlencoded')
        self.assertEqual(req.get_data(parse_form_data=True), b'')
        self.assertEqual(req.form['foo'], u'Hello World')

    def test_common_request_descriptors_mixin(self):
        request = Request.from_values(
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
        request = Request.from_values(content_type='APPLICATION/JSON')
        self.assertEqual(request.mimetype, 'application/json')

    def test_shallow_mode(self):
        request = Request({'QUERY_STRING': 'foo=bar'}, shallow=True)
        self.assertEqual(request.args['foo'], 'bar')
        self.assertRaises(RuntimeError, lambda: request.form['foo'])

    def test_form_parsing_failed(self):
        data = (
            b'--blah\r\n'
        )
        data = Request.from_values(
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
        req = Request.from_values(
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
        req = Request.from_values(
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
        req = Request.from_values()
        req.charset = 'utf-7'
        self.assertEqual(req.url_charset, 'utf-7')

    def test_other_method_payload(self):
        data = b'Hello World'
        req = Request.from_values(
            input_stream=BytesIO(data), method='WHAT_THE_FUCK',
            content_length=len(data), content_type='text/plain'
        )
        self.assertEqual(req.get_data(), data)
        self.assertTrue(isinstance(req.stream, LimitedStream))

    def test_form_data_ordering(self):
        class MyRequest(Request):
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
        class MyRequest(Request):
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

        req = Request.from_values(headers={
            'Cookie':   'foo=bar'
        })
        self.assertIs(type(req.cookies), ImmutableTypeConversionDict)
        self.assertEqual(req.cookies, {'foo': 'bar'})
        self.assertIs(type(req.access_route), ImmutableList)

        MyRequest.list_storage_class = tuple
        req = MyRequest.from_values()
        self.assertIs(type(req.access_route), tuple)

    def test_modified_url_encoding(self):
        class ModifiedRequest(Request):
            url_charset = 'euc-kr'

        req = ModifiedRequest.from_values(u'/?foo=정상처리'.encode('euc-kr'))
        self.assertEqual(req.args['foo'], u'정상처리')

    def test_request_method_case_sensitivity(self):
        req = Request({'REQUEST_METHOD': 'get'})
        self.assertEqual(req.method, 'GET')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RequestsTestCase))
    return suite
