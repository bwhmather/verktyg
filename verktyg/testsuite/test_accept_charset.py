"""
    verktyg.testsuite.test_accept_charset
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for HTTP accept header parsing utilities.


    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from verktyg.accept.charset import (
    parse_charset_header, parse_accept_charset_header,
    Charset, CharsetAccept,
)
from verktyg.exceptions import NotAcceptable


class CharsetTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = parse_accept_charset_header(
            'iso-8859-5'
        )

        range_ = next(iter(accept))
        self.assertEqual('iso-8859-5', range_.value)
        self.assertEqual(1, range_.q)

    def test_parse_accept_q(self):
        accept = parse_accept_charset_header(
            'ascii;q=0.5',
        )

        range_ = next(iter(accept))
        self.assertEqual('ascii', range_.value)
        self.assertEqual(0.5, range_.q)

    def test_parse_accept_params(self):
        with self.assertRaises(ValueError):
            parse_accept_charset_header(
                'utf-8;orange=black'
            )

    def test_parse_accept_multiple(self):
        accept = parse_accept_charset_header(
            'utf-8,'
            'ascii;q=0.5,'
            '*;q=0.1'
        )

        self.assertEqual(3, len(list(accept)))

    def test_parse(self):
        charset = parse_charset_header('utf-8')
        self.assertEqual('utf-8', charset.value)

    def test_serialize(self):
        charset = Charset('iso-8859-1', qs=0.5)
        self.assertEqual('iso-8859-1', charset.to_header())

    def test_serialize_accept(self):
        accept = CharsetAccept(['ascii'])
        self.assertEqual(accept.to_header(), 'ascii')

    def test_serialize_accept_with_q(self):
        accept = CharsetAccept([('utf-8', '0.5')])
        self.assertEqual(accept.to_header(), 'utf-8;q=0.5')

    def test_serialize_accept_redundant_q(self):
        accept = CharsetAccept([('utf-8', '1')])
        self.assertEqual(accept.to_header(), 'utf-8')

    def test_serialize_accept_multiple(self):
        accept = CharsetAccept([
            'utf-8',
            ('ascii', 0.5),
            ('*', 0.1),
        ])
        self.assertEqual(
            accept.to_header(),
            (
                'utf-8,'
                'ascii;q=0.5,'
                '*;q=0.1'
            )
        )

    def test_match_basic(self):
        accept = CharsetAccept(['utf-8'])

        acceptable = Charset('utf-8')
        unacceptable = Charset('latin-1')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.charset)
        self.assertTrue(match.exact_match)

    def test_match_wildcard(self):
        accept = CharsetAccept(['*'])

        charset = Charset('iso-8859-8')

        match = charset.acceptability(accept)
        self.assertEqual(charset, match.charset)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = CharsetAccept([('utf-8', '0.5')])

        no_qs = Charset('utf-8')
        qs = Charset('utf-8', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = CharsetAccept([
            'utf-8',
            ('ascii', 0.5),
            ('*', 0.1),
        ])

        charset = Charset('utf-8')
        match = charset.acceptability(accept)
        self.assertEqual(1.0, match.quality)
        self.assertTrue(match.exact_match)

        charset = Charset('ascii')
        match = charset.acceptability(accept)
        self.assertEqual(0.5, match.quality)
        self.assertTrue(match.exact_match)

        charset = Charset('latin-1')
        match = charset.acceptability(accept)
        self.assertEqual(0.1, match.quality)
        self.assertFalse(match.exact_match)
