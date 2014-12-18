"""
    verktyg.testsuite
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

import werkzeug.testsuite as wzt


suite = unittest.TestSuite()
for other_suite in wzt.iter_suites(__name__):
    suite.addTest(other_suite)
