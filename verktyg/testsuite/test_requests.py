"""
    tests.requests
    ~~~~~~~~~~~~~~

    Tests for request objects.

    :copyright:
        (c) 2017 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

import pickle
from io import BytesIO
from datetime import datetime

from verktyg.datastructures import (
    MultiDict, ImmutableList,
    ImmutableTypeConversionDict,
)
from verktyg.test import Client
from verktyg.wsgi import LimitedStream
from verktyg.exceptions import SecurityError
from verktyg.requests import BaseRequest, Request
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
        'args': request.args,
        'args_as_list': list(request.args.lists()),
        'environ': prepare_environ_pickle(request.environ),
        'data': request.get_data()
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
        self.assertEqual(response['data'], b'')
        self.assert_environ(response['environ'], 'GET')

        # post requests with json data
        json = b'{"foo": "bar", "blub": "blah"}'
        response = client.post(
            '/?a=b', data=json, content_type='application/json'
        )
        self.assertEqual(response['data'], json)
        self.assertEqual(response['args'], MultiDict([('a', u'b')]))

    def test_query_string_is_bytes(self):
        req = Request.from_values(u'/?foo=%2f')
        self.assertEqual(req.query_string, 'foo=%2f')

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

    def test_etag_request_mixin(self):
        request = Request({
            'HTTP_CACHE_CONTROL': 'no-store, no-cache',
            'HTTP_IF_MATCH': 'w/"foo", bar, "baz"',
            'HTTP_IF_NONE_MATCH': 'w/"foo", bar, "baz"',
            'HTTP_IF_MODIFIED_SINCE': 'Tue, 22 Jan 2008 11:18:44 GMT',
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

    def test_common_request_descriptors_mixin(self):
        request = Request.from_values(
            content_type='text/html; charset=utf-8',
            content_length='23',
            headers={
                'Referer': 'http://www.example.com/',
                'Date': 'Sat, 28 Feb 2009 19:04:35 GMT',
                'Max-Forwards': '10',
                'Pragma': 'no-cache',
                'Content-Encoding': 'gzip',
                'Content-MD5': '9a3bc6dbc47a70db25b84c6e5867a072'
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

    def test_other_method_payload(self):
        data = b'Hello World'
        req = Request.from_values(
            input_stream=BytesIO(data), method='WHAT_THE_FUCK',
            content_length=len(data), content_type='text/plain'
        )
        self.assertEqual(req.get_data(), data)
        self.assertTrue(isinstance(req.stream, LimitedStream))

    def test_storage_classes(self):
        class MyRequest(Request):
            dict_storage_class = dict
            list_storage_class = list
            parameter_storage_class = dict
        req = MyRequest.from_values('/?foo=baz', headers={
            'Cookie': 'foo=bar'
        })
        self.assertIs(type(req.cookies), dict)
        self.assertEqual(req.cookies, {'foo': 'bar'})
        self.assertIs(type(req.access_route), list)

        self.assertIs(type(req.args), dict)

        req = Request.from_values(headers={
            'Cookie': 'foo=bar'
        })
        self.assertIs(type(req.cookies), ImmutableTypeConversionDict)
        self.assertEqual(req.cookies, {'foo': 'bar'})
        self.assertIs(type(req.access_route), ImmutableList)

        MyRequest.list_storage_class = tuple
        req = MyRequest.from_values()
        self.assertIs(type(req.access_route), tuple)

    def test_request_method_case_sensitivity(self):
        req = Request({'REQUEST_METHOD': 'get'})
        self.assertEqual(req.method, 'GET')
