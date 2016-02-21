"""
    verktyg.testsuite.utils
    ~~~~~~~~~~~~~~~~~~~~~~~

    General utilities.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from datetime import datetime
import inspect

from verktyg.responses import BaseResponse
from verktyg.test import Client
from verktyg.http import parse_date, http_date
from verktyg import utils


class UtilsTestCase(unittest.TestCase):
    def test_redirect(self):
        resp = utils.redirect(u'/füübär')
        self.assertIn(b'/f%C3%BC%C3%BCb%C3%A4r', resp.get_data())
        self.assertEqual(resp.headers['Location'], '/f%C3%BC%C3%BCb%C3%A4r')
        self.assertEqual(resp.status_code, 302)

        resp = utils.redirect(u'http://☃.net/', 307)
        self.assertIn(b'http://xn--n3h.net/', resp.get_data())
        self.assertEqual(resp.headers['Location'], 'http://xn--n3h.net/')
        self.assertEqual(resp.status_code, 307)

        resp = utils.redirect('http://example.com/', 305)
        self.assertEqual(resp.headers['Location'], 'http://example.com/')
        self.assertEqual(resp.status_code, 305)

    def test_redirect_no_unicode_header_keys(self):
        # Make sure all headers are native keys.  This was a bug at one point
        # due to an incorrect conversion.
        resp = utils.redirect('http://example.com/', 305)
        for key, value in resp.headers.items():
            self.assertEqual(type(key), str)
            self.assertEqual(type(value), str)
        self.assertEqual(resp.headers['Location'], 'http://example.com/')
        self.assertEqual(resp.status_code, 305)

    def test_redirect_xss(self):
        location = 'http://example.com/?xss="><script>alert(1)</script>'
        resp = utils.redirect(location)
        self.assertNotIn(b'<script>alert(1)</script>', resp.get_data())

        location = 'http://example.com/?xss="onmouseover="alert(1)'
        resp = utils.redirect(location)
        self.assertNotIn(
            b'href="http://example.com/?xss="onmouseover="alert(1)"',
            resp.get_data()
        )

    def test_redirect_with_custom_response_class(self):
        class MyResponse(BaseResponse):
            pass

        location = "http://example.com/redirect"
        resp = utils.redirect(location, Response=MyResponse)

        self.assertIsInstance(resp, MyResponse)
        self.assertEqual(resp.headers['Location'], location)

    def test_cached_property(self):
        foo = []

        class A(object):

            def prop(self):
                foo.append(42)
                return 42
            prop = utils.cached_property(prop)

        a = A()
        p = a.prop
        q = a.prop
        self.assertEqual(p, q, 42)
        self.assertEqual(foo, [42])

        foo = []

        class A(object):

            def _prop(self):
                foo.append(42)
                return 42
            prop = utils.cached_property(_prop, name='prop')
            del _prop

        a = A()
        p = a.prop
        q = a.prop
        self.assertEqual(p, q, 42)
        self.assertEqual(foo, [42])

    def test_can_set_cached_property(self):
        class A(object):

            @utils.cached_property
            def _prop(self):
                return 'cached_property return value'

        a = A()
        a._prop = 'value'
        self.assertEqual(a._prop, 'value')

    def test_inspect_treats_cached_property_as_property(self):
        class A(object):

            @utils.cached_property
            def _prop(self):
                return 'cached_property return value'

        attrs = inspect.classify_class_attrs(A)
        for attr in attrs:
            if attr.name == '_prop':
                break
        self.assertEqual(attr.kind, 'property')

    def test_environ_property(self):
        class A(object):
            environ = {'string': 'abc', 'number': '42'}

            string = utils.environ_property(
                'string'
            )
            missing = utils.environ_property(
                'missing', 'spam'
            )
            read_only = utils.environ_property(
                'number'
            )
            number = utils.environ_property(
                'number', load_func=int
            )
            broken_number = utils.environ_property(
                'broken_number', load_func=int
            )
            date = utils.environ_property(
                'date', None, parse_date, http_date, read_only=False
            )
            foo = utils.environ_property(
                'foo'
            )

        a = A()
        self.assertEqual(a.string, 'abc')
        self.assertEqual(a.missing, 'spam')

        def test_assign():
            a.read_only = 'something'
        self.assertRaises(AttributeError, test_assign)
        self.assertEqual(a.number, 42)
        self.assertIs(a.broken_number, None)
        self.assertIs(a.date, None)
        a.date = datetime(2008, 1, 22, 10, 0, 0, 0)
        self.assertEqual(a.environ['date'], 'Tue, 22 Jan 2008 10:00:00 GMT')

    def test_append_slash_redirect(self):
        def app(env, sr):
            return utils.append_slash_redirect(env)(env, sr)
        client = Client(app, BaseResponse)
        response = client.get('foo', base_url='http://example.org/app')
        self.assertEqual(
            response.status_code, 301
        )
        self.assertEqual(
            response.headers['Location'], 'http://example.org/app/foo/'
        )

    def test_cached_property_doc(self):
        @utils.cached_property
        def foo():
            """testing"""
            return 42
        self.assertEqual(foo.__doc__, 'testing')
        self.assertEqual(foo.__name__, 'foo')
        self.assertEqual(foo.__module__, __name__)

    def test_secure_filename(self):
        self.assertEqual(
            utils.secure_filename('My cool movie.mov'),
            'My_cool_movie.mov'
        )
        self.assertEqual(
            utils.secure_filename('../../../etc/passwd'),
            'etc_passwd'
        )
        self.assertEqual(
            utils.secure_filename(u'i contain cool \xfcml\xe4uts.txt'),
            'i_contain_cool_umlauts.txt'
        )
