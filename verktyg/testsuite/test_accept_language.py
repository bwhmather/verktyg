"""
    verktyg.testsuite.test_accept_language
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for HTTP accept header parsing utilities.


    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from verktyg.accept.language import (
    parse_language_header, parse_accept_language_header,
    Language, LanguageAccept,
)

from verktyg.exceptions import NotAcceptable


class LanguageTestCase(unittest.TestCase):
    def test_parse_accept_basic(self):
        accept = parse_accept_language_header('en-gb')

        range_ = next(iter(accept))
        self.assertEqual('en-gb', range_.value)
        self.assertEqual(1, range_.q)

    def test_parse_accept_params(self):
        self.assertRaises(
            ValueError, parse_accept_language_header, 'en;param=invalid'
        )

    def test_parse_accept_q(self):
        accept = parse_accept_language_header('en; q=0.8')
        range_ = next(iter(accept))

        self.assertEqual(0.8, range_.q)

    def test_parse_accept_multiple(self):
        accept = parse_accept_language_header(
            'da,en-gb;q=0.8,en;q=0.7,*;q=0.1'
        )

        self.assertEqual(len(list(accept)), 4)

    def test_parse(self):
        language = parse_language_header('en-gb')

        self.assertEqual(language.value, 'en-gb')

    def test_serialize(self):
        language = Language('en-us', qs=0.5)

        self.assertEqual('en-us', language.to_header())

    def test_serialize_accept_redundant_q(self):
        accept = LanguageAccept([('jp', '1')])
        self.assertEqual(accept.to_header(), 'jp')

    def test_serialize_accept_multiple(self):
        accept = LanguageAccept([
            'da', ('en-gb', 0.8), ('en', 0.7), ('*', 0.1)
        ])

        self.assertEqual(accept.to_header(), 'da,en-gb;q=0.8,en;q=0.7,*;q=0.1')

    def test_match_basic(self):
        accept = LanguageAccept(['en-gb'])

        acceptable = Language('en-gb')
        unacceptable = Language('fr')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(match.language, acceptable)
        self.assertEqual(match.specificity, 2)
        self.assertEqual(match.tail, 0)
        self.assertTrue(match.exact_match)

    def test_match_partial(self):
        accept = LanguageAccept(['one-two'])

        unacceptable = Language('one')
        acceptable = Language('one-two-three')

        self.assertRaises(NotAcceptable, unacceptable.acceptability, accept)

        match = acceptable.acceptability(accept)
        self.assertEqual(acceptable, match.language)
        self.assertEqual(match.specificity, 2)
        self.assertEqual(match.tail, 1)
        self.assertFalse(match.exact_match)

    def test_match_wildcard(self):
        accept = LanguageAccept(['*'])

        language = Language('en')

        match = language.acceptability(accept)
        self.assertEqual(match.language, language)
        self.assertEqual(match.specificity, 0)
        self.assertEqual(match.tail, 1)
        self.assertFalse(match.exact_match)

    def test_match_quality(self):
        accept = LanguageAccept([('en', '0.5')])

        no_qs = Language('en')
        qs = Language('en', qs=0.5)

        self.assertEqual(0.5, no_qs.acceptability(accept).quality)
        self.assertEqual(0.25, qs.acceptability(accept).quality)

    def test_match(self):
        accept = LanguageAccept([
            'fr', 'fr-be', ('en-gb', 0.8), ('en', 0.7), ('*', 0.1)
        ])

        fr = Language('fr')
        fr_match = fr.acceptability(accept)
        self.assertEqual(fr_match.quality, 1.0)
        self.assertTrue(fr_match.exact_match)

        fr_be = Language('fr-be')
        fr_be_match = fr_be.acceptability(accept)
        self.assertEqual(fr_be_match.quality, 1.0)
        self.assertTrue(fr_be_match.exact_match)

        # more specific first
        self.assertGreater(fr_be_match, fr_match)

        en_gb = Language('en-gb')
        en_gb_match = en_gb.acceptability(accept)
        self.assertEqual(en_gb_match.quality, 0.8)
        self.assertTrue(en_gb_match.exact_match)

        en_us = Language('en-us')
        en_us_match = en_us.acceptability(accept)
        self.assertEqual(en_us_match.quality, 0.7)
        self.assertFalse(en_us_match.exact_match)

        en = Language('en')
        en_match = en.acceptability(accept)
        self.assertEqual(en_match.quality, 0.7)
        self.assertTrue(en_match.exact_match)

        zu = Language('zu')
        zu_match = zu.acceptability(accept)
        self.assertEqual(zu_match.quality, 0.1)
        self.assertFalse(zu_match.exact_match)
