"""
    verktyg.testsuite
    ~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.

"""
import unittest

from verktyg.testsuite import (
    test_utils, test_datastructures, test_exceptions, test_http,
    test_accept_content_type, test_accept_language, test_accept_charset,
    test_accept, test_wsgi, test_requests, test_responses, test_routing,
    test_dispatch,  test_views, test_application,
)


loader = unittest.TestLoader()
suite = unittest.TestSuite((
    loader.loadTestsFromModule(test_utils),
    loader.loadTestsFromModule(test_datastructures),
    loader.loadTestsFromModule(test_exceptions),
    loader.loadTestsFromModule(test_http),
    loader.loadTestsFromModule(test_wsgi),
    loader.loadTestsFromModule(test_requests),
    loader.loadTestsFromModule(test_responses),
    loader.loadTestsFromModule(test_routing),
    loader.loadTestsFromModule(test_dispatch),
    loader.loadTestsFromModule(test_accept_content_type),
    loader.loadTestsFromModule(test_accept_language),
    loader.loadTestsFromModule(test_accept_charset),
    loader.loadTestsFromModule(test_accept),
    loader.loadTestsFromModule(test_views),
    loader.loadTestsFromModule(test_application),
))
