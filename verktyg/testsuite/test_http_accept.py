"""
    verktyg.testsuite.test_http_accept
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for HTTP accept header parsing utilities.


    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from verktyg import http


class AcceptTestCase(unittest.TestCase):
    def test_accept_basic(self):
        accept = http.Accept([
            ('tinker', 0), ('tailor', 0.333),
            ('soldier', 0.667), ('sailor', 1),
        ])
        # check __getitem__ on indices
        self.assertEqual(accept[3], ('tinker', 0))
        self.assertEqual(accept[2], ('tailor', 0.333))
        self.assertEqual(accept[1], ('soldier', 0.667))
        self.assertEqual(accept[0], ('sailor', 1))
        # check __getitem__ on string
        self.assertEqual(accept['tinker'], 0)
        self.assertEqual(accept['tailor'], 0.333)
        self.assertEqual(accept['soldier'], 0.667)
        self.assertEqual(accept['sailor'], 1)
        self.assertEqual(accept['spy'], 0)
        # check quality method
        self.assertEqual(accept.quality('tinker'), 0)
        self.assertEqual(accept.quality('tailor'), 0.333)
        self.assertEqual(accept.quality('soldier'), 0.667)
        self.assertEqual(accept.quality('sailor'), 1)
        self.assertEqual(accept.quality('spy'), 0)
        # check __contains__
        self.assertIn('sailor', accept)
        self.assertNotIn('spy', accept)
        # check index method
        self.assertEqual(accept.index('tinker'), 3)
        self.assertEqual(accept.index('tailor'), 2)
        self.assertEqual(accept.index('soldier'), 1)
        self.assertEqual(accept.index('sailor'), 0)
        self.assertRaises(ValueError, accept.index, 'spy')
        # check find method
        self.assertEqual(accept.find('tinker'), 3)
        self.assertEqual(accept.find('tailor'), 2)
        self.assertEqual(accept.find('soldier'), 1)
        self.assertEqual(accept.find('sailor'), 0)
        self.assertEqual(accept.find('spy'), -1)
        # check to_header method
        self.assertEqual(
            accept.to_header(),
            'sailor,soldier;q=0.667,tailor;q=0.333,tinker;q=0'
        )
        # check best_match method
        self.assertEqual(
            accept.best_match(
                ['tinker', 'tailor', 'soldier', 'sailor'], default=None
            ),
            'sailor'
        )
        self.assertEqual(
            accept.best_match(['tinker', 'tailor', 'soldier'], default=None),
            'soldier'
        )
        self.assertEqual(
            accept.best_match(['tinker', 'tailor'], default=None),
            'tailor'
        )
        self.assertIs(accept.best_match(['tinker'], default=None), None)
        self.assertEqual(accept.best_match(['tinker'], default='x'), 'x')

    def test_accept_wildcard(self):
        accept = http.Accept([('*', 0), ('asterisk', 1)])
        self.assertIn('*', accept)
        self.assertEqual(
            accept.best_match(['asterisk', 'star'], default=None),
            'asterisk'
        )
        self.assertIs(accept.best_match(['star'], default=None), None)

    def test_parse_accept(self):
        a = http.parse_accept_header('en-us,ru;q=0.5')
        self.assertEqual(list(a.values()), ['en-us', 'ru'])
        self.assertEqual(a.best, 'en-us')
        self.assertEqual(a.find('ru'), 1)
        self.assertRaises(ValueError, a.index, 'de')
        self.assertEqual(a.to_header(), 'en-us,ru;q=0.5')

    def test_parse_mime_accept(self):
        a = http.parse_accept_header(
            'text/xml,application/xml,'
            'application/xhtml+xml,'
            'application/foo;quiet=no; bar=baz;q=0.6,'
            'text/html;q=0.9,text/plain;q=0.8,'
            'image/png,*/*;q=0.5',
            http.MIMEAccept
        )
        self.assertRaises(ValueError, lambda: a['missing'])
        self.assertEqual(a['image/png'], 1)
        self.assertEqual(a['text/plain'], 0.8)
        self.assertEqual(a['foo/bar'], 0.5)
        self.assertEqual(a['application/foo;quiet=no; bar=baz'], 0.6)
        self.assertEqual(a[a.find('foo/bar')], ('*/*', 0.5))

    def test_accept_matches(self):
        a = http.parse_accept_header(
            'text/xml,application/xml,application/xhtml+xml,'
            'text/html;q=0.9,text/plain;q=0.8,'
            'image/png', http.MIMEAccept
        )
        self.assertEqual(
            a.best_match(['text/html', 'application/xhtml+xml']),
            'application/xhtml+xml'
        )
        self.assertEqual(a.best_match(['text/html']), 'text/html')
        self.assertIs(a.best_match(['foo/bar']), None)
        self.assertEqual(
            a.best_match(['foo/bar', 'bar/foo'], default='foo/bar'), 'foo/bar'
        )
        self.assertEqual(
            a.best_match(['application/xml', 'text/xml']), 'application/xml'
        )

    def test_parse_charset_accept(self):
        a = http.parse_accept_header(
            'ISO-8859-1,utf-8;q=0.7,*;q=0.7', http.CharsetAccept
        )
        self.assertEqual(a['iso-8859-1'], a['iso8859-1'])
        self.assertEqual(a['iso-8859-1'], 1)
        self.assertEqual(a['UTF8'], 0.7)
        self.assertEqual(a['ebcdic'], 0.7)

    def test_parse_language_accept(self):
        a = http.parse_accept_header(
            'de-AT,de;q=0.8,en;q=0.5', http.LanguageAccept
        )
        self.assertEqual(a.best, 'de-AT')
        self.assertIn('de_AT', a)
        self.assertIn('en', a)
        self.assertEqual(a['de-at'], 1)
        self.assertEqual(a['en'], 0.5)
