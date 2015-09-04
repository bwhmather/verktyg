"""
    verktyg.testsuite.accept
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for choosing representations based on content type, etc.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from verktyg import http
from verktyg.exceptions import NotAcceptable
from verktyg.accept import Representation, select_representation


class RepresentationTestCase(unittest.TestCase):
    def test_content_type_dispatch(self):
        accept = http.parse_accept_header(
            'text/xml,'
            'application/xml,'
            'application/xhtml+xml,'
            'application/foo;q=0.6;quiet=no;bar=baz,'
            'text/html;q=0.9,'
            'text/plain;q=0.8,'
            'image/png,'
            '*/*;q=0.5'
        )

        default_repr = Representation()
        png_repr = Representation(content_type='image/png')
        plain_repr = Representation(content_type='text/plain')
        json_repr = Representation(content_type='application/json')

        default_match = default_repr.acceptability(accept=accept)
        png_match = png_repr.acceptability(accept=accept)
        plain_match = plain_repr.acceptability(accept=accept)
        json_match = json_repr.acceptability(accept=accept)

        self.assertLess(default_match, png_match)
        self.assertLess(default_match, plain_match)
        self.assertLess(default_match, json_match)
        self.assertGreater(png_match, plain_match)
        self.assertGreater(png_match, json_match)
        self.assertGreater(plain_match, json_match)

    def test_select_representation(self):
        json_repr = Representation(content_type='application/json')
        html_repr = Representation(content_type='text/html')
        xml_repr = Representation(content_type='application/xml')
        blank_repr = Representation()

        representations = [json_repr, html_repr, xml_repr, blank_repr]

        self.assertEqual(
            json_repr, select_representation(
                representations, accept='application/json'
            )
        )

        self.assertEqual(
            xml_repr,
            select_representation(
                representations,
                accept='application/xml;q=0.9,text/html;q=0.8'
            )
        )

        self.assertEqual(
            blank_repr,
            select_representation(
                representations, accept='image/png'
            )
        )


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RepresentationTestCase))
    return suite
