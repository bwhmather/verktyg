"""
    verktyg.testsuite.test_http
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for HTTP parsing utilities.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from datetime import datetime

from werkzeug._compat import wsgi_encoding_dance

from verktyg import http
from verktyg.test import create_environ


class HeadersTestCase(unittest.TestCase):
    storage_class = http.Headers

    def test_basic_interface(self):
        headers = self.storage_class()
        headers.add('Content-Type', 'text/plain')
        headers.add('X-Foo', 'bar')
        self.assertIn('x-Foo', headers)
        self.assertIn('Content-type', headers)

        headers['Content-Type'] = 'foo/bar'
        self.assertEqual(headers['Content-Type'], 'foo/bar')
        self.assertEqual(len(headers.getlist('Content-Type')), 1)

        # list conversion
        self.assertEqual(headers.to_wsgi_list(), [
            ('Content-Type', 'foo/bar'),
            ('X-Foo', 'bar')
        ])
        self.assertEqual(str(headers), (
            "Content-Type: foo/bar\r\n"
            "X-Foo: bar\r\n"
            "\r\n"
        ))
        self.assertEqual(str(self.storage_class()), "\r\n")

        # extended add
        headers.add('Content-Disposition', 'attachment', filename='foo')
        self.assertEqual(
            headers['Content-Disposition'], 'attachment; filename=foo'
        )

        headers.add('x', 'y', z='"')
        self.assertEqual(headers['x'], r'y; z="\""')

    def test_header_set_duplication_bug(self):
        headers = self.storage_class([
            ('Content-Type', 'text/html'),
            ('Foo', 'bar'),
            ('Blub', 'blah')
        ])
        headers['blub'] = 'hehe'
        headers['blafasel'] = 'humm'
        self.assertEqual(headers, self.storage_class([
            ('Content-Type', 'text/html'),
            ('Foo', 'bar'),
            ('blub', 'hehe'),
            ('blafasel', 'humm')
        ]))

    def test_defaults_and_conversion(self):
        # defaults
        headers = self.storage_class([
            ('Content-Type', 'text/plain'),
            ('X-Foo',        'bar'),
            ('X-Bar',        '1'),
            ('X-Bar',        '2')
        ])
        self.assertEqual(headers.getlist('x-bar'), ['1', '2'])
        self.assertEqual(headers.get('x-Bar'), '1')
        self.assertEqual(headers.get('Content-Type'), 'text/plain')

        self.assertEqual(headers.setdefault('X-Foo', 'nope'), 'bar')
        self.assertEqual(headers.setdefault('X-Bar', 'nope'), '1')
        self.assertEqual(headers.setdefault('X-Baz', 'quux'), 'quux')
        self.assertEqual(headers.setdefault('X-Baz', 'nope'), 'quux')
        headers.pop('X-Baz')

        # type conversion
        self.assertEqual(headers.get('x-bar', type=int), 1)
        self.assertEqual(headers.getlist('x-bar', type=int), [1, 2])

        # list like operations
        self.assertEqual(headers[0], ('Content-Type', 'text/plain'))
        self.assertEqual(headers[:1], self.storage_class(
            [('Content-Type', 'text/plain')]
        ))
        del headers[:2]
        del headers[-1]
        self.assertEqual(headers, self.storage_class([('X-Bar', '1')]))

    def test_copying(self):
        a = self.storage_class([('foo', 'bar')])
        b = a.copy()
        a.add('foo', 'baz')
        self.assertEqual(a.getlist('foo'), ['bar', 'baz'])
        self.assertEqual(b.getlist('foo'), ['bar'])

    def test_popping(self):
        headers = self.storage_class([('a', 1)])
        self.assertEqual(headers.pop('a'), 1)
        self.assertEqual(headers.pop('b', 2), 2)

        self.assertRaises(KeyError, headers.pop, 'c')

    def test_set_arguments(self):
        a = self.storage_class()
        a.set('Content-Disposition', 'useless')
        a.set('Content-Disposition', 'attachment', filename='foo')
        self.assertEqual(a['Content-Disposition'], 'attachment; filename=foo')

    def test_reject_newlines(self):
        h = self.storage_class()

        for variation in 'foo\nbar', 'foo\r\nbar', 'foo\rbar':
            try:
                h['foo'] = variation
            except ValueError:
                pass
            else:
                self.fail()

            try:
                h.add('foo', variation)
            except ValueError:
                pass
            else:
                self.fail()

            try:
                h.add('foo', 'test', option=variation)
            except ValueError:
                pass
            else:
                self.fail()

            try:
                h.set('foo', variation)
            except ValueError:
                pass
            else:
                self.fail()

            try:
                h.set('foo', 'test', option=variation)
            except ValueError:
                pass
            else:
                self.fail()

    def test_slicing(self):
        # there's nothing wrong with these being native strings
        # Headers doesn't care about the data types
        h = self.storage_class()
        h.set('X-Foo-Poo', 'bleh')
        h.set('Content-Type', 'application/whocares')
        h.set('X-Forwarded-For', '192.168.0.123')
        h[:] = [(k, v) for k, v in h if k.startswith(u'X-')]
        self.assertEqual(list(h), [
            ('X-Foo-Poo', 'bleh'),
            ('X-Forwarded-For', '192.168.0.123')
        ])

    def test_bytes_operations(self):
        h = self.storage_class()
        h.set('X-Foo-Poo', 'bleh')
        h.set('X-Whoops', b'\xff')

        self.assertEqual(h.get('x-foo-poo', as_bytes=True), b'bleh')
        self.assertEqual(h.get('x-whoops', as_bytes=True), b'\xff')

    def test_to_wsgi_list(self):
        h = self.storage_class()
        h.set(u'Key', u'Value')
        for key, value in h.to_wsgi_list():
            self.assertEqual(key, u'Key')
            self.assertEqual(value, u'Value')


class HTTPUtilityTestCase(unittest.TestCase):
    def test_list_header(self):
        hl = http.parse_list_header('foo baz, blah')
        self.assertEqual(hl, ['foo baz', 'blah'])

    def test_dict_header(self):
        d = http.parse_dict_header('foo="bar baz", blah=42')
        self.assertEqual(d, {'foo': 'bar baz', 'blah': '42'})

    def test_etags_nonzero(self):
        etags = http.parse_etags('w/"foo"')
        assert bool(etags)
        assert etags.contains_raw('w/"foo"')

    def test_parse_date(self):
        self.assertEqual(
            http.parse_date('Sun, 06 Nov 1994 08:49:37 GMT    '),
            datetime(1994, 11, 6, 8, 49, 37)
        )
        self.assertEqual(
            http.parse_date('Sunday, 06-Nov-94 08:49:37 GMT'),
            datetime(1994, 11, 6, 8, 49, 37)
        )
        self.assertEqual(http.parse_date(
            ' Sun Nov  6 08:49:37 1994'),
            datetime(1994, 11, 6, 8, 49, 37)
        )
        self.assertIs(http.parse_date('foo'), None)

    def test_parse_date_overflows(self):
        self.assertEqual(
            http.parse_date(' Sun 02 Feb 1343 08:49:37 GMT'),
            datetime(1343, 2, 2, 8, 49, 37)
        )
        self.assertEqual(
            http.parse_date('Thu, 01 Jan 1970 00:00:00 GMT'),
            datetime(1970, 1, 1, 0, 0)
        )
        self.assertIs(http.parse_date('Thu, 33 Jan 1970 00:00:00 GMT'), None)

    def test_remove_entity_headers(self):
        now = http.http_date()
        headers1 = [
            ('Date', now),
            ('Content-Type', 'text/html'),
            ('Content-Length', '0'),
        ]
        headers2 = http.Headers(headers1)

        http.remove_entity_headers(headers1)
        self.assertEqual(headers1, [('Date', now)])

        http.remove_entity_headers(headers2)
        self.assertEqual(headers2, http.Headers([(u'Date', now)]))

    def test_remove_hop_by_hop_headers(self):
        headers1 = [
            ('Connection', 'closed'),
            ('Foo', 'bar'),
            ('Keep-Alive', 'wtf'),
        ]
        headers2 = http.Headers(headers1)

        http.remove_hop_by_hop_headers(headers1)
        self.assertEqual(headers1, [('Foo', 'bar')])

        http.remove_hop_by_hop_headers(headers2)
        self.assertEqual(headers2, http.Headers([('Foo', 'bar')]))

    def test_parse_options_header(self):
        self.assertEqual(
            http.parse_options_header(r'something; foo="other\"thing"'),
            ('something', {'foo': 'other"thing'})
        )
        self.assertEqual(
            http.parse_options_header(
                r'something; foo="other\"thing"; meh=42'
            ),
            ('something', {'foo': 'other"thing', 'meh': '42'})
        )
        self.assertEqual(
            http.parse_options_header(
                r'something; foo="other\"thing"; meh=42; bleh'
            ),
            ('something', {'foo': 'other"thing', 'meh': '42', 'bleh': None})
        )
        self.assertEqual(
            http.parse_options_header(
                'something; foo="other;thing"; meh=42; bleh'
            ),
            ('something', {'foo': 'other;thing', 'meh': '42', 'bleh': None})
        )
        self.assertEqual(
            http.parse_options_header(
                'something; foo="otherthing"; meh=; bleh'
            ),
            ('something', {'foo': 'otherthing', 'meh': None, 'bleh': None})
        )

    def test_dump_options_header(self):
        self.assertEqual(
            http.dump_options_header('foo', {'bar': 42}), 'foo; bar=42'
        )
        self.assertIn(
            http.dump_options_header('foo', {'bar': 42, 'fizz': None}),
            ('foo; bar=42; fizz', 'foo; fizz; bar=42')
        )

    def test_dump_header(self):
        self.assertEqual(http.dump_header([1, 2, 3]), '1, 2, 3')
        self.assertEqual(
            http.dump_header([1, 2, 3], allow_token=False), '"1", "2", "3"'
        )
        self.assertEqual(
            http.dump_header({'foo': 'bar'}, allow_token=False), 'foo="bar"'
        )
        self.assertEqual(http.dump_header({'foo': 'bar'}), 'foo=bar')

    def test_is_resource_modified(self):
        env = create_environ()

        # ignore POST
        env['REQUEST_METHOD'] = 'POST'
        self.assertFalse(http.is_resource_modified(env, etag='testing'))
        env['REQUEST_METHOD'] = 'GET'

        # etagify from data
        self.assertRaises(
            TypeError, http.is_resource_modified, env, data='42', etag='23'
        )
        env['HTTP_IF_NONE_MATCH'] = http.generate_etag(b'awesome')
        self.assertFalse(http.is_resource_modified(env, data=b'awesome'))

        env['HTTP_IF_MODIFIED_SINCE'] = http.http_date(
            datetime(2008, 1, 1, 12, 30)
        )
        self.assertFalse(
            http.is_resource_modified(
                env, last_modified=datetime(2008, 1, 1, 12, 00)
            )
        )
        self.assertTrue(
            http.is_resource_modified(
                env, last_modified=datetime(2008, 1, 1, 13, 00)
            )
        )

    def test_date_formatting(self):
        self.assertEqual(
            http.cookie_date(0),
            'Thu, 01-Jan-1970 00:00:00 GMT'
        )
        self.assertEqual(
            http.cookie_date(datetime(1970, 1, 1)),
            'Thu, 01-Jan-1970 00:00:00 GMT'
        )
        self.assertEqual(
            http.http_date(0),
            'Thu, 01 Jan 1970 00:00:00 GMT'
        )
        self.assertEqual(
            http.http_date(datetime(1970, 1, 1)),
            'Thu, 01 Jan 1970 00:00:00 GMT'
        )

    def test_cookies(self):
        self.assertEqual(
            dict(
                http.parse_cookie(
                    'dismiss-top=6; CP=null*; '
                    'PHPSESSID=0a539d42abc001cdc762809248d4beed; '
                    'a=42; b="\\\";"'
                )
            ),
            {
                'CP':           u'null*',
                'PHPSESSID':    u'0a539d42abc001cdc762809248d4beed',
                'a':            u'42',
                'dismiss-top':  u'6',
                'b':            u'\";'
            }
        )
        rv = http.dump_cookie(
            'foo', 'bar baz blub', 360, httponly=True, sync_expires=False
        )
        self.assertIs(type(rv), str)
        self.assertEqual(
            set(rv.split('; ')),
            {
                'HttpOnly',
                'Max-Age=360',
                'Path=/',
                'foo="bar baz blub"'
            }
        )

        self.assertEqual(
            dict(http.parse_cookie('fo234{=bar; blub=Blah')),
            {'fo234{': u'bar', 'blub': u'Blah'}
        )

    def test_cookie_quoting(self):
        val = http.dump_cookie("foo", "?foo")
        self.assertEqual(val, 'foo="?foo"; Path=/')
        self.assertEqual(dict(http.parse_cookie(val)), {'foo': u'?foo'})

        self.assertEqual(
            dict(http.parse_cookie(r'foo="foo\054bar"')),
            {'foo': u'foo,bar'}
        )

    def test_cookie_domain_resolving(self):
        val = http.dump_cookie('foo', 'bar', domain=u'\N{SNOWMAN}.com')
        self.assertEqual(val, 'foo=bar; Domain=xn--n3h.com; Path=/')

    def test_cookie_unicode_dumping(self):
        val = http.dump_cookie('foo', u'\N{SNOWMAN}')
        h = http.Headers()
        h.add('Set-Cookie', val)
        self.assertEqual(h['Set-Cookie'], 'foo="\\342\\230\\203"; Path=/')

        cookies = http.parse_cookie(h['Set-Cookie'])
        self.assertEqual(cookies['foo'], u'\N{SNOWMAN}')

    def test_cookie_unicode_keys(self):
        # Yes, this is technically against the spec but happens
        val = http.dump_cookie(u'fö', u'fö')
        self.assertEqual(
            val, wsgi_encoding_dance(u'fö="f\\303\\266"; Path=/', 'utf-8')
        )
        cookies = http.parse_cookie(val)
        self.assertEqual(cookies[u'fö'], u'fö')

    def test_cookie_unicode_parsing(self):
        # This is actually a correct test.  This is what is being submitted
        # by firefox if you set an unicode cookie and we get the cookie sent
        # in on Python 3 under PEP 3333.
        cookies = http.parse_cookie(u'fÃ¶=fÃ¶')
        self.assertEqual(cookies[u'fö'], u'fö')

    def test_cookie_domain_encoding(self):
        val = http.dump_cookie('foo', 'bar', domain=u'\N{SNOWMAN}.com')
        self.assertEqual(val, 'foo=bar; Domain=xn--n3h.com; Path=/')

        val = http.dump_cookie('foo', 'bar', domain=u'.\N{SNOWMAN}.com')
        self.assertEqual(val, 'foo=bar; Domain=.xn--n3h.com; Path=/')

        val = http.dump_cookie('foo', 'bar', domain=u'.foo.com')
        self.assertEqual(val, 'foo=bar; Domain=.foo.com; Path=/')


class IfRangeTestCase(unittest.TestCase):
    def test_parse_if_range_header(self):
        rv = http.parse_if_range_header('"Test"')
        self.assertEqual(rv.etag, 'Test')
        self.assertIs(rv.date, None)
        self.assertEqual(rv.to_header(), '"Test"')

        # weak information is dropped
        rv = http.parse_if_range_header('w/"Test"')
        self.assertEqual(rv.etag, 'Test')
        self.assertIs(rv.date, None)
        self.assertEqual(rv.to_header(), '"Test"')

        # broken etags are supported too
        rv = http.parse_if_range_header('bullshit')
        self.assertEqual(rv.etag, 'bullshit')
        self.assertIs(rv.date, None)
        self.assertEqual(rv.to_header(), '"bullshit"')

        rv = http.parse_if_range_header('Thu, 01 Jan 1970 00:00:00 GMT')
        self.assertIs(rv.etag, None)
        self.assertEqual(rv.date, datetime(1970, 1, 1))
        self.assertEqual(rv.to_header(), 'Thu, 01 Jan 1970 00:00:00 GMT')

        for x in '', None:
            rv = http.parse_if_range_header(x)
            self.assertIs(rv.etag, None)
            self.assertIs(rv.date, None)
            self.assertEqual(rv.to_header(), '')


class RangeTestCase(unittest.TestCase):
    def test_parse_range(self):
        rv = http.parse_range_header('bytes=52')
        self.assertIs(rv, None)

        rv = http.parse_range_header('bytes=52-')
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.ranges, [(52, None)])
        self.assertEqual(rv.to_header(), 'bytes=52-')

        rv = http.parse_range_header('bytes=52-99')
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.ranges, [(52, 100)])
        self.assertEqual(rv.to_header(), 'bytes=52-99')

        rv = http.parse_range_header('bytes=52-99,-1000')
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.ranges, [(52, 100), (-1000, None)])
        self.assertEqual(rv.to_header(), 'bytes=52-99,-1000')

        rv = http.parse_range_header('bytes = 1 - 100')
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.ranges, [(1, 101)])
        self.assertEqual(rv.to_header(), 'bytes=1-100')

        rv = http.parse_range_header('AWesomes=0-999')
        self.assertEqual(rv.units, 'awesomes')
        self.assertEqual(rv.ranges, [(0, 1000)])
        self.assertEqual(rv.to_header(), 'awesomes=0-999')


class ContentRangeTestCase(unittest.TestCase):
    def test_parse_content_range(self):
        rv = http.parse_content_range_header('bytes 0-98/*')
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.start, 0)
        self.assertEqual(rv.stop, 99)
        self.assertIs(rv.length, None)
        self.assertEqual(rv.to_header(), 'bytes 0-98/*')

        rv = http.parse_content_range_header('bytes 0-98/*asdfsa')
        self.assertIs(rv, None)

        rv = http.parse_content_range_header('bytes 0-99/100')
        self.assertEqual(rv.to_header(), 'bytes 0-99/100')
        rv.start = None
        rv.stop = None
        self.assertEqual(rv.units, 'bytes')
        self.assertEqual(rv.to_header(), 'bytes */100')

        rv = http.parse_content_range_header('bytes */100')
        self.assertIs(rv.start, None)
        self.assertIs(rv.stop, None)
        self.assertEqual(rv.length, 100)
        self.assertEqual(rv.units, 'bytes')


class HeaderSetTestCase(unittest.TestCase):
    def test_basic_interface(self):
        hs = http.HeaderSet()
        hs.add('foo')
        hs.add('bar')
        self.assertIn('Bar', hs)
        self.assertEqual(hs.find('foo'), 0)
        self.assertEqual(hs.find('BAR'), 1)
        self.assertLess(hs.find('baz'), 0)
        hs.discard('missing')
        hs.discard('foo')
        self.assertLess(hs.find('foo'), 0)
        self.assertEqual(hs.find('bar'), 0)

        self.assertRaises(IndexError, hs.index, 'missing')

        self.assertEqual(hs.index('bar'), 0)
        self.assertTrue(hs)
        hs.clear()
        self.assertFalse(hs)

    def test_parse_set_header(self):
        hs = http.parse_set_header('foo, Bar, "Blah baz", Hehe')
        self.assertIn('blah baz', hs)
        self.assertNotIn('foobar', hs)
        self.assertIn('foo', hs)
        self.assertEqual(list(hs), ['foo', 'Bar', 'Blah baz', 'Hehe'])
        hs.add('Foo')
        self.assertEqual(hs.to_header(), 'foo, Bar, "Blah baz", Hehe')


class CacheControlTestCase(unittest.TestCase):
    def test_repr(self):
        cc = http.RequestCacheControl(
            [("max-age", "0"), ("private", "True")],
        )
        self.assertEqual(
            repr(cc), "<RequestCacheControl max-age='0' private='True'>"
        )

    def test_cache_control_header(self):
        cc = http.parse_cache_control_header('max-age=0, no-cache')
        self.assertEqual(cc.max_age, 0)
        self.assertTrue(cc.no_cache)
        cc = http.parse_cache_control_header(
            'private, community="UCI"', None,
            http.ResponseCacheControl
        )
        self.assertTrue(cc.private)
        self.assertEqual(cc['community'], 'UCI')

        c = http.ResponseCacheControl()
        self.assertIs(c.no_cache, None)
        self.assertIs(c.private, None)
        c.no_cache = True
        self.assertEqual(c.no_cache, '*')
        c.private = True
        self.assertEqual(c.private, '*')
        del c.private
        self.assertIs(c.private, None)
        self.assertEqual(c.to_header(), 'no-cache')


class ETagsTestCase(unittest.TestCase):
    def test_parse_etags(self):
        self.assertEqual(http.quote_etag('foo'), '"foo"')
        self.assertEqual(http.quote_etag('foo', True), 'w/"foo"')
        self.assertEqual(http.unquote_etag('"foo"'), ('foo', False))
        self.assertEqual(http.unquote_etag('w/"foo"'), ('foo', True))
        es = http.parse_etags('"foo", "bar", w/"baz", blar')
        self.assertEqual(sorted(es), ['bar', 'blar', 'foo'])
        self.assertIn('foo', es)
        self.assertNotIn('baz', es)
        assert es.contains_weak('baz')
        self.assertIn('blar', es)
        assert es.contains_raw('w/"baz"')
        assert es.contains_raw('"foo"')
        self.assertEqual(
            sorted(es.to_header().split(', ')),
            ['"bar"', '"blar"', '"foo"', 'w/"baz"']
        )


class AuthorizationTestCase(unittest.TestCase):
    def test_parse_authorization_header(self):
        a = http.parse_authorization_header(
            'Basic QWxhZGRpbjpvcGVuIHNlc2FtZQ=='
        )
        self.assertEqual(a.type, 'basic')
        self.assertEqual(a.username, 'Aladdin')
        self.assertEqual(a.password, 'open sesame')

        a = http.parse_authorization_header(
            'Digest username="Mufasa", '
            'realm="testrealm@host.invalid", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
            'uri="/dir/index.html", '
            'qop=auth, '
            'nc=00000001, '
            'cnonce="0a4f113b", '
            'response="6629fae49393a05397450978507c4ef1", '
            'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
        self.assertEqual(a.type, 'digest')
        self.assertEqual(a.username, 'Mufasa')
        self.assertEqual(a.realm, 'testrealm@host.invalid')
        self.assertEqual(a.nonce, 'dcd98b7102dd2f0e8b11d0f600bfb0c093')
        self.assertEqual(a.uri, '/dir/index.html')
        self.assertIn('auth', a.qop)
        self.assertEqual(a.nc, '00000001')
        self.assertEqual(a.cnonce, '0a4f113b')
        self.assertEqual(a.response, '6629fae49393a05397450978507c4ef1')
        self.assertEqual(a.opaque, '5ccc069c403ebaf9f0171e9517f40e41')

        a = http.parse_authorization_header(
            'Digest username="Mufasa", '
            'realm="testrealm@host.invalid", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
            'uri="/dir/index.html", '
            'response="e257afa1414a3340d93d30955171dd0e", '
            'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
        self.assertEqual(a.type, 'digest')
        self.assertEqual(a.username, 'Mufasa')
        self.assertEqual(a.realm, 'testrealm@host.invalid')
        self.assertEqual(a.nonce, 'dcd98b7102dd2f0e8b11d0f600bfb0c093')
        self.assertEqual(a.uri, '/dir/index.html')
        self.assertEqual(a.response, 'e257afa1414a3340d93d30955171dd0e')
        self.assertEqual(a.opaque, '5ccc069c403ebaf9f0171e9517f40e41')

        self.assertIs(http.parse_authorization_header(''), None)
        self.assertIs(http.parse_authorization_header(None), None)
        self.assertIs(http.parse_authorization_header('foo'), None)


class WWWAuthenticateTestCase(unittest.TestCase):
    def test_parse_www_authenticate_header(self):
        wa = http.parse_www_authenticate_header('Basic realm="WallyWorld"')
        self.assertEqual(wa.type, 'basic')
        self.assertEqual(wa.realm, 'WallyWorld')
        wa.realm = 'Foo Bar'
        self.assertEqual(wa.to_header(), 'Basic realm="Foo Bar"')

        wa = http.parse_www_authenticate_header(
            'Digest '
            'realm="testrealm@host.com", '
            'qop="auth,auth-int", '
            'nonce="dcd98b7102dd2f0e8b11d0f600bfb0c093", '
            'opaque="5ccc069c403ebaf9f0171e9517f40e41"'
        )
        self.assertEqual(wa.type, 'digest')
        self.assertEqual(wa.realm, 'testrealm@host.com')
        self.assertIn('auth', wa.qop)
        self.assertIn('auth-int', wa.qop)
        self.assertEqual(wa.nonce, 'dcd98b7102dd2f0e8b11d0f600bfb0c093')
        self.assertEqual(wa.opaque, '5ccc069c403ebaf9f0171e9517f40e41')

        wa = http.parse_www_authenticate_header('broken')
        self.assertEqual(wa.type, 'broken')

        assert not http.parse_www_authenticate_header('').type
        assert not http.parse_www_authenticate_header('')


class FileStorageTestCase(object):
    def test_mimetype_always_lowercase(self):
        file_storage = http.FileStorage(content_type='APPLICATION/JSON')
        self.assertEqual(file_storage.mimetype, 'application/json')
