"""
    verktyg.testsuite.test_headers
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.

"""
import unittest

from verktyg.headers import Headers, EnvironHeaders, HeaderSet


class HeadersTestCase(unittest.TestCase):
    storage_class = Headers

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


class EnvironHeadersTestCase(unittest.TestCase):
    storage_class = EnvironHeaders

    def test_basic_interface(self):
        # this happens in multiple WSGI servers because they
        # use a vary naive way to convert the headers;
        broken_env = {
            'HTTP_CONTENT_TYPE':        'text/html',
            'CONTENT_TYPE':             'text/html',
            'HTTP_CONTENT_LENGTH':      '0',
            'CONTENT_LENGTH':           '0',
            'HTTP_ACCEPT':              '*',
            'wsgi.version':             (1, 0)
        }
        headers = self.storage_class(broken_env)
        self.assertTrue(headers)
        self.assertEqual(len(headers), 3)
        self.assertEqual(sorted(headers), [
            ('Accept', '*'),
            ('Content-Length', '0'),
            ('Content-Type', 'text/html')
        ])
        self.assertFalse(self.storage_class({'wsgi.version': (1, 0)}))
        self.assertEqual(len(self.storage_class({'wsgi.version': (1, 0)})), 0)

    def test_return_type_is_unicode(self):
        # environ contains native strings; we return unicode
        headers = self.storage_class({
            'HTTP_FOO': '\xe2\x9c\x93',
            'CONTENT_TYPE': 'text/plain',
        })
        self.assertEqual(headers['Foo'], u"\xe2\x9c\x93")
        self.assertIsInstance(headers['Foo'], str)
        self.assertIsInstance(headers['Content-Type'], str)
        iter_output = dict(iter(headers))
        self.assertEqual(iter_output['Foo'], u"\xe2\x9c\x93")
        self.assertIsInstance(iter_output['Foo'], str)
        self.assertIsInstance(iter_output['Content-Type'], str)

    def test_bytes_operations(self):
        foo_val = '\xff'
        h = self.storage_class({
            'HTTP_X_FOO': foo_val
        })

        self.assertEqual(h.get('x-foo', as_bytes=True), b'\xff')
        self.assertEqual(h.get('x-foo'), u'\xff')


class HeaderSetTestCase(unittest.TestCase):
    storage_class = HeaderSet

    def test_basic_interface(self):
        hs = self.storage_class()
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
