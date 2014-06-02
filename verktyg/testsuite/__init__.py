"""
    verktyg.testsuite
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Contains all Dispatcher tests.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

import werkzeug.testsuite as wzt


class BetterLoader(wzt.BetterLoader):
    """Werkzeug loader saves werkzeug root suite in closure.  This just
    overrides it.
    """
    def getRootSuite(self):
        return suite()


def suite():
    suite = unittest.TestSuite()
    for other_suite in wzt.iter_suites(__name__):
        suite.addTest(other_suite)
    return suite


def main():
    try:
        unittest.main(testLoader=BetterLoader(), defaultTest='suite')
    except Exception:
        import sys
        import traceback
        traceback.print_exc()
        sys.exit(1)
