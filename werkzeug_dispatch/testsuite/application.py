# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.testsuite.application
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests `Application` utility class.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug import Response
from werkzeug.routing import Rule

from werkzeug_dispatch.views import expose
from werkzeug_dispatch.application import Application


class ApplicationTestCase(WerkzeugTestCase):
    def test_basic(self):
        app = Application()

        app.add_routes(Rule('/', endpoint='index'))

        @expose(app.dispatcher, 'index')
        def index(app, request):
            return Response('Hello World')


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApplicationTestCase))
    return suite
