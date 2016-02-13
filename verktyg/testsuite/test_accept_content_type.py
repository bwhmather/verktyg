"""
    verktyg.testsuite.test_accept_content_type
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for HTTP accept header parsing utilities.


    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from verktyg.accept.content_type import (
    parse_content_type_header, parse_accept_header,
    ContentType, ContentTypeAccept,
)
from verktyg.exceptions import NotAcceptable


class ContentTypeTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = parse_accept_header(
            'text/xml'
        )

        range_ = next(iter(accept))
        self.assertEqual('text', range_.type)
        self.assertEqual('xml', range_.subtype)
        self.assertEqual(1, range_.q)
        self.assertEqual(0, len(range_.params))
        with self.assertRaises(KeyError):
            range_.params['q']

    def test_parse_accept_params(self):
        accept = parse_accept_header(
            'application/foo;quiet=no; bar=baz;q=0.6'
        )
        range_ = next(iter(accept))
        self.assertEqual('application', range_.type)
        self.assertEqual('foo', range_.subtype)
        self.assertEqual(0.6, range_.q)

        self.assertEqual(2, len(range_.params))
        self.assertEqual('no', range_.params['quiet'])
        self.assertEqual('baz', range_.params['bar'])
        with self.assertRaises(KeyError):
            range_.params['no-such-param']
        with self.assertRaises(KeyError):
            range_.params['q']

    def test_parse_accept_invalid_params(self):
        # TODO
        pass

    def test_parse_accept_case(self):
        # TODO
        pass

    def test_parse_accept_multiple(self):
        accept = parse_accept_header(
            'text/xml,'
            'application/xml,'
            'application/xhtml+xml,'
            'application/foo;quiet=no; bar=baz;q=0.6,'
            'text/html;q=0.9,'
            'text/plain;q=0.8,'
            'image/png,'
            '*/*;q=0.5'
        )

        self.assertEqual(len(list(accept)), 8)

    def test_parse(self):
        content_type = parse_content_type_header('text/html')

        self.assertEqual(content_type.type, 'text')
        self.assertEqual(content_type.subtype, 'html')

    def test_serialize(self):
        content_type = ContentType('text/html', qs=0.5)

        self.assertEqual('text/html', content_type.to_header())

    def test_serialize_accept(self):
        accept = ContentTypeAccept(['text/html'])

        self.assertEqual(accept.to_header(), 'text/html')

    def test_serialize_accept_q_before_params(self):
        accept = ContentTypeAccept([
            ('application/json', '0.5', {'speed': 'maximum'}),
        ])

        self.assertEqual(
            accept.to_header(), 'application/json;q=0.5;speed=maximum'
        )

    def test_serialize_accept_redundant_q(self):
        accept = ContentTypeAccept([('image/png', '1')])
        self.assertEqual(accept.to_header(), 'image/png')

    def test_serialize_accept_multiple(self):
        accept = ContentTypeAccept([
            'application/xhtml+xml',
            ('text/plain', '0.8'),
            'image/png',
            ('*/*', '0.5'),
        ])
        self.assertEqual(
            accept.to_header(),
            (
                'application/xhtml+xml,'
                'text/plain;q=0.8,'
                'image/png,'
                '*/*;q=0.5'
            )
        )

    def test_match_basic(self):
        accept = ContentTypeAccept(['text/xml'])

        acceptable = ContentType('text/xml')
        unacceptable_type = ContentType('application/xml')
        unacceptable_subtype = ContentType('text/html')

        self.assertRaises(
            NotAcceptable, unacceptable_type.acceptability, accept
        )
        self.assertRaises(
            NotAcceptable, unacceptable_subtype.acceptability, accept
        )

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.content_type)
        self.assertTrue(match.type_matches)
        self.assertTrue(match.subtype_matches)
        self.assertTrue(match.exact_match)

    def test_match_wildcard(self):
        accept = ContentTypeAccept(['*/*'])

        content_type = ContentType('text/html')

        match = content_type.acceptability(accept)
        self.assertEqual(content_type, match.content_type)
        self.assertFalse(match.type_matches)
        self.assertFalse(match.subtype_matches)
        self.assertFalse(match.exact_match)

    def test_match_subtype_wildcard(self):
        accept = ContentTypeAccept(['text/*'])

        unacceptable = ContentType('image/jpeg')
        acceptable = ContentType('text/html')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.content_type)
        self.assertTrue(match.type_matches)
        self.assertFalse(match.subtype_matches)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = ContentTypeAccept([('text/html', '0.5')])

        no_qs = ContentType('text/html')
        qs = ContentType('text/html', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = ContentTypeAccept([
            'text/xml',
            'application/xml',
            'application/xhtml+xml',
            ('application/foo', '0.6', {'quiet': 'no', 'bar': 'baz'}),
            ('text/html', '0.9'),
            ('text/plain', '0.8'),
            'image/png',
            ('*/*', '0.5'),
        ])

        content_type = ContentType('image/png')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 1.0)
        self.assertTrue(match.exact_match)

        content_type = ContentType('text/plain')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 0.8)
        self.assertTrue(match.exact_match)

        content_type = ContentType('application/json')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 0.5)
        self.assertFalse(match.exact_match)
