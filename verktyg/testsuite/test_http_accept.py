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
from verktyg.exceptions import NotAcceptable


class ContentTypeTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = http.parse_accept_header(
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
        accept = http.parse_accept_header(
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
        accept = http.parse_accept_header(
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
        content_type = http.parse_content_type_header('text/html')

        self.assertEqual(content_type.type, 'text')
        self.assertEqual(content_type.subtype, 'html')

    def test_serialize(self):
        content_type = http.ContentType('text/html', qs=0.5)

        self.assertEqual('text/html', content_type.to_header())

    def test_serialize_accept(self):
        accept = http.ContentTypeAccept(['text/html'])

        self.assertEqual(accept.to_header(), 'text/html')

    def test_serialize_accept_q_before_params(self):
        accept = http.ContentTypeAccept([
            ('application/json', '0.5', {'speed': 'maximum'}),
        ])

        self.assertEqual(
            accept.to_header(), 'application/json;q=0.5;speed=maximum'
        )

    def test_serialize_accept_redundant_q(self):
        accept = http.ContentTypeAccept([('image/png', '1')])
        self.assertEqual(accept.to_header(), 'image/png')

    def test_serialize_accept_multiple(self):
        accept = http.ContentTypeAccept([
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
        accept = http.ContentTypeAccept(['text/xml'])

        acceptable = http.ContentType('text/xml')
        unacceptable_type = http.ContentType('application/xml')
        unacceptable_subtype = http.ContentType('text/html')

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
        accept = http.ContentTypeAccept(['*/*'])

        content_type = http.ContentType('text/html')

        match = content_type.acceptability(accept)
        self.assertEqual(content_type, match.content_type)
        self.assertFalse(match.type_matches)
        self.assertFalse(match.subtype_matches)
        self.assertFalse(match.exact_match)

    def test_match_subtype_wildcard(self):
        accept = http.ContentTypeAccept(['text/*'])

        unacceptable = http.ContentType('image/jpeg')
        acceptable = http.ContentType('text/html')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.content_type)
        self.assertTrue(match.type_matches)
        self.assertFalse(match.subtype_matches)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = http.ContentTypeAccept([('text/html', '0.5')])

        no_qs = http.ContentType('text/html')
        qs = http.ContentType('text/html', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = http.ContentTypeAccept([
            'text/xml',
            'application/xml',
            'application/xhtml+xml',
            ('application/foo', '0.6', {'quiet': 'no', 'bar': 'baz'}),
            ('text/html', '0.9'),
            ('text/plain', '0.8'),
            'image/png',
            ('*/*', '0.5'),
        ])

        content_type = http.ContentType('image/png')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 1.0)
        self.assertTrue(match.exact_match)

        content_type = http.ContentType('text/plain')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 0.8)
        self.assertTrue(match.exact_match)

        content_type = http.ContentType('application/json')
        match = content_type.acceptability(accept)
        self.assertEqual(match.quality, 0.5)
        self.assertFalse(match.exact_match)


class LanguageTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = http.parse_accept_language_header('en-gb')

        range_ = next(iter(accept))
        self.assertEqual('en-gb', range_.value)
        self.assertEqual(1, range_.q)

    def test_parse_accept_params(self):
        self.assertRaises(
            ValueError, http.parse_accept_language_header, 'en;param=invalid'
        )

    def test_parse_accept_q(self):
        accept = http.parse_accept_language_header('en; q=0.8')
        range_ = next(iter(accept))

        self.assertEqual(0.8, range_.q)

    def test_parse_accept_multiple(self):
        accept = http.parse_accept_language_header(
            'da,en-gb;q=0.8,en;q=0.7,*;q=0.1'
        )

        self.assertEqual(len(list(accept)), 4)

    def test_parse(self):
        language = http.parse_language_header('en-gb')

        self.assertEqual(language.value, 'en-gb')

    def test_serialize(self):
        language = http.Language('en-us', qs=0.5)

        self.assertEqual('en-us', language.to_header())

    def test_serialize_accept_redundant_q(self):
        accept = http.LanguageAccept([('jp', '1')])
        self.assertEqual(accept.to_header(), 'jp')

    def test_serialize_accept_multiple(self):
        accept = http.LanguageAccept([
            'da', ('en-gb', 0.8), ('en', 0.7), ('*', 0.1)
        ])

        self.assertEqual(accept.to_header(), 'da,en-gb;q=0.8,en;q=0.7,*;q=0.1')

    def test_match_basic(self):
        accept = http.LanguageAccept(['en-gb'])

        acceptable = http.Language('en-gb')
        unacceptable = http.Language('fr')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(match.language, acceptable)
        self.assertEqual(match.specificity, 2)
        self.assertEqual(match.tail, 0)
        self.assertTrue(match.exact_match)

    def test_match_partial(self):
        accept = http.LanguageAccept(['one-two'])

        unacceptable = http.Language('one')
        acceptable = http.Language('one-two-three')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.language)
        self.assertEqual(match.specificity, 2)
        self.assertEqual(match.tail, 1)
        self.assertFalse(match.exact_match)

    def test_match_wildcard(self):
        accept = http.LanguageAccept(['*'])

        language = http.Language('en')

        match = language.acceptability(accept)
        self.assertEqual(match.language, language)
        self.assertEqual(match.specificity, 0)
        self.assertEqual(match.tail, 1)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = http.LanguageAccept([('en', '0.5')])

        no_qs = http.Language('en')
        qs = http.Language('en', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = http.LanguageAccept([
            'fr', 'fr-be', ('en-gb', 0.8), ('en', 0.7), ('*', 0.1)
        ])

        fr = http.Language('fr')
        fr_match = fr.acceptability(accept)
        self.assertEqual(fr_match.quality, 1.0)
        self.assertTrue(fr_match.exact_match)

        fr_be = http.Language('fr-be')
        fr_be_match = fr_be.acceptability(accept)
        self.assertEqual(fr_be_match.quality, 1.0)
        self.assertTrue(fr_be_match.exact_match)

        # more specific first
        self.assertGreater(fr_be_match, fr_match)

        en_gb = http.Language('en-gb')
        en_gb_match = en_gb.acceptability(accept)
        self.assertEqual(en_gb_match.quality, 0.8)
        self.assertTrue(en_gb_match.exact_match)

        en_us = http.Language('en-us')
        en_us_match = en_us.acceptability(accept)
        self.assertEqual(en_us_match.quality, 0.7)
        self.assertFalse(en_us_match.exact_match)

        en = http.Language('en')
        en_match = en.acceptability(accept)
        self.assertEqual(en_match.quality, 0.7)
        self.assertTrue(en_match.exact_match)

        zu = http.Language('zu')
        zu_match = zu.acceptability(accept)
        self.assertEqual(zu_match.quality, 0.1)
        self.assertFalse(zu_match.exact_match)


class CharsetTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = http.parse_accept_charset_header(
            'iso-8859-5'
        )

        range_ = next(iter(accept))
        self.assertEqual('iso-8859-5', range_.value)
        self.assertEqual(1, range_.q)

    def test_parse_accept_q(self):
        accept = http.parse_accept_charset_header(
            'ascii;q=0.5',
        )

        range_ = next(iter(accept))
        self.assertEqual('ascii', range_.value)
        self.assertEqual(0.5, range_.q)

    def test_parse_accept_params(self):
        with self.assertRaises(ValueError):
            http.parse_accept_charset_header(
                'utf-8;orange=black'
            )

    def test_parse_accept_multiple(self):
        accept = http.parse_accept_charset_header(
            'utf-8,'
            'ascii;q=0.5,'
            '*;q=0.1'
        )

        self.assertEqual(3, len(list(accept)))

    def test_parse(self):
        charset = http.parse_charset_header('utf-8')
        self.assertEqual('utf-8', charset.value)

    def test_serialize(self):
        charset = http.Charset('iso-8859-1', qs=0.5)
        self.assertEqual('iso-8859-1', charset.to_header())

    def test_serialize_accept(self):
        accept = http.CharsetAccept(['ascii'])
        self.assertEqual(accept.to_header(), 'ascii')

    def test_serialize_accept_with_q(self):
        accept = http.CharsetAccept([('utf-8', '0.5')])
        self.assertEqual(accept.to_header(), 'utf-8;q=0.5')

    def test_serialize_accept_redundant_q(self):
        accept = http.CharsetAccept([('utf-8', '1')])
        self.assertEqual(accept.to_header(), 'utf-8')

    def test_serialize_accept_multiple(self):
        accept = http.CharsetAccept([
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
        accept = http.CharsetAccept(['utf-8'])

        acceptable = http.Charset('utf-8')
        unacceptable = http.Charset('latin-1')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.charset)
        self.assertTrue(match.exact_match)

    def test_match_wildcard(self):
        accept = http.CharsetAccept(['*'])

        charset = http.Charset('iso-8859-8')

        match = charset.acceptability(accept)
        self.assertEqual(charset, match.charset)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = http.CharsetAccept([('utf-8', '0.5')])

        no_qs = http.Charset('utf-8')
        qs = http.Charset('utf-8', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = http.CharsetAccept([
            'utf-8',
            ('ascii', 0.5),
            ('*', 0.1),
        ])

        charset = http.Charset('utf-8')
        match = charset.acceptability(accept)
        self.assertEqual(1.0, match.quality)
        self.assertTrue(match.exact_match)

        charset = http.Charset('ascii')
        match = charset.acceptability(accept)
        self.assertEqual(0.5, match.quality)
        self.assertTrue(match.exact_match)

        charset = http.Charset('latin-1')
        match = charset.acceptability(accept)
        self.assertEqual(0.1, match.quality)
        self.assertFalse(match.exact_match)
