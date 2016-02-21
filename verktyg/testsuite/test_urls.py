"""
    verktyg.testsuite.test_urls
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    URL helper tests.

    :copyright:
        (c) 2016 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from verktyg import urls


class UrlsTestCase(unittest.TestCase):

    def test_url_fixing(self):
        x = urls.url_fix(
            'http://de.wikipedia.org/wiki/Elf (Begriffskl\xe4rung)'
        )
        self.assertEqual(
            x, 'http://de.wikipedia.org/wiki/Elf%20(Begriffskl%C3%A4rung)'
        )

        x = urls.url_fix("http://just.a.test/$-_.+!*'(),")
        self.assertEqual(x, "http://just.a.test/$-_.+!*'(),")

        x = urls.url_fix('http://höhöhö.at/höhöhö/hähähä')
        self.assertEqual(
            x,
            (
                r'http://xn--hhh-snabb.at'
                r'/h%C3%B6h%C3%B6h%C3%B6/h%C3%A4h%C3%A4h%C3%A4'
            )
        )

    def test_url_fixing_filepaths(self):
        x = urls.url_fix(r'file://C:\Users\Administrator\My Documents\ÑÈáÇíí')
        self.assertEqual(
            x,
            (
                r'file:///C%3A/Users/Administrator/My%20Documents/'
                r'%C3%91%C3%88%C3%A1%C3%87%C3%AD%C3%AD'
            )
        )

        a = urls.url_fix(r'file:/C:/')
        b = urls.url_fix(r'file://C:/')
        c = urls.url_fix(r'file:///C:/')
        self.assertEqual(a, r'file:///C%3A/')
        self.assertEqual(b, r'file:///C%3A/')
        self.assertEqual(c, r'file:///C%3A/')

        x = urls.url_fix(r'file://host/sub/path')
        self.assertEqual(x, r'file://host/sub/path')

        x = urls.url_fix(r'file:///')
        self.assertEqual(x, r'file:///')

    def test_url_fixing_qs(self):
        x = urls.url_fix('http://example.com/?foo=%2f%2f')
        self.assertEqual(x, 'http://example.com/?foo=%2f%2f')

        x = urls.url_fix(
            'http://acronyms.thefreedictionary.com/'
            'Algebraic+Methods+of+Solving+the+Schr%C3%B6dinger+Equation'
        )
        self.assertEqual(
            x,
            (
                'http://acronyms.thefreedictionary.com/'
                'Algebraic+Methods+of+Solving+the+Schr%C3%B6dinger+Equation'
            )
        )

    def test_iri_support(self):
        self.assertEqual(
            urls.uri_to_iri('http://xn--n3h.net/'),
            'http://\u2603.net/'
        )
        self.assertEqual(
            urls.uri_to_iri(
                'http://%C3%BCser:p%C3%A4ssword@xn--n3h.net/p%C3%A5th'
            ),
            'http://\xfcser:p\xe4ssword@\u2603.net/p\xe5th'
        )
        self.assertEqual(
            urls.iri_to_uri('http://☃.net/'),
            'http://xn--n3h.net/'
        )
        self.assertEqual(
            urls.iri_to_uri('http://üser:pässword@☃.net/påth'),
            'http://%C3%BCser:p%C3%A4ssword@xn--n3h.net/p%C3%A5th'
        )

        self.assertEqual(
            urls.uri_to_iri('http://test.com/%3Fmeh?foo=%26%2F'),
            'http://test.com/%3Fmeh?foo=%26%2F'
        )

        self.assertEqual(urls.iri_to_uri('/foo'), '/foo')

        self.assertEqual(
            urls.iri_to_uri('http://föö.com:8080/bam/baz'),
            'http://xn--f-1gaa.com:8080/bam/baz'
        )

    def test_iri_safe_quoting(self):
        uri = 'http://xn--f-1gaa.com/%2F%25?q=%C3%B6&x=%3D%25#%25'
        iri = 'http://föö.com/%2F%25?q=ö&x=%3D%25#%25'
        self.assertEqual(urls.uri_to_iri(uri), iri)
        self.assertEqual(urls.iri_to_uri(urls.uri_to_iri(uri)), uri)

    def test_iri_to_uri_idempotence_ascii_only(self):
        uri = 'http://www.idempoten.ce'
        uri = urls.iri_to_uri(uri)
        self.assertEqual(urls.iri_to_uri(uri), uri)

    def test_iri_to_uri_idempotence_non_ascii(self):
        uri = 'http://\N{SNOWMAN}/\N{SNOWMAN}'
        uri = urls.iri_to_uri(uri)
        self.assertEqual(urls.iri_to_uri(uri), uri)

    def test_uri_to_iri_idempotence_ascii_only(self):
        uri = 'http://www.idempoten.ce'
        uri = urls.uri_to_iri(uri)
        self.assertEqual(urls.uri_to_iri(uri), uri)

    def test_uri_to_iri_idempotence_non_ascii(self):
        uri = 'http://xn--n3h/%E2%98%83'
        uri = urls.uri_to_iri(uri)
        self.assertEqual(urls.uri_to_iri(uri), uri)

    def test_iri_to_uri_to_iri(self):
        iri = 'http://föö.com/'
        uri = urls.iri_to_uri(iri)
        self.assertEqual(urls.uri_to_iri(uri), iri)

    def test_uri_to_iri_to_uri(self):
        uri = 'http://xn--f-rgao.com/%C3%9E'
        iri = urls.uri_to_iri(uri)
        self.assertEqual(urls.iri_to_uri(iri), uri)

    def test_uri_iri_normalization(self):
        uri = 'http://xn--f-rgao.com/%E2%98%90/fred?utf8=%E2%9C%93'
        iri = 'http://föñ.com/\N{BALLOT BOX}/fred?utf8=\u2713'

        tests = [
            'http://föñ.com/\N{BALLOT BOX}/fred?utf8=\u2713',
            'http://xn--f-rgao.com/\u2610/fred?utf8=\N{CHECK MARK}',
            'http://xn--f-rgao.com/%E2%98%90/fred?utf8=%E2%9C%93',
            'http://xn--f-rgao.com/%E2%98%90/fred?utf8=%E2%9C%93',
            'http://föñ.com/\u2610/fred?utf8=%E2%9C%93',
        ]

        for test in tests:
            self.assertEqual(urls.uri_to_iri(test), iri)
            self.assertEqual(urls.iri_to_uri(test), uri)
            self.assertEqual(urls.uri_to_iri(urls.iri_to_uri(test)), iri)
            self.assertEqual(urls.iri_to_uri(urls.uri_to_iri(test)), uri)
            self.assertEqual(urls.uri_to_iri(urls.uri_to_iri(test)), iri)
            self.assertEqual(urls.iri_to_uri(urls.iri_to_uri(test)), uri)
