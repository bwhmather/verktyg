# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.testsuite.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for the core dispatcher.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug.wrappers import Response
from werkzeug.datastructures import Accept
from werkzeug.exceptions import NotFound, MethodNotAllowed, NotAcceptable

from werkzeug_dispatch.bindings import Binding
import werkzeug_dispatch as d


class DispatchTestCase(WerkzeugTestCase):
    def test_name_dispatch(self):
        dispatcher = d.Dispatcher([
            Binding('tweedle-dum', 'Tweedle Dum'),
            Binding('tweedle-dee', 'Tweedle Dee'),
            Binding('same', 'overridden'),
            Binding('same', 'overriding'),
            ])

        self.assert_equal('Tweedle Dum', dispatcher.lookup('tweedle-dum'))
        self.assert_equal('Tweedle Dee', dispatcher.lookup('tweedle-dee'))
        self.assert_raises(NotFound, dispatcher.lookup, 'non-existant')
        self.assert_equal('overriding', dispatcher.lookup('same'))

    def test_method_dispatch(self):
        dispatcher = d.Dispatcher([
            Binding('test', 'get', method='GET'),
            Binding('test', 'post', method='POST'),
            Binding('head', 'head', method='HEAD'),
            Binding('no-head', 'get', method='GET'),

            Binding('same', 'overridden'),
            Binding('same', 'unaffected', method='POST'),
            Binding('same', 'overriding'),
            ])

        # default to 'GET'
        self.assert_equal('get', dispatcher.lookup('test'))
        self.assert_equal('get', dispatcher.lookup('test', method='GET'))

        # `POST` gives something different
        self.assert_equal('post', dispatcher.lookup('test', method='POST'))

        # `PUT` not found
        self.assert_raises(MethodNotAllowed, dispatcher.lookup, 'test', method='PUT')

        # `HEAD` should fall back to `GET`
        self.assert_equal('head', dispatcher.lookup('head', method='HEAD'))
        self.assert_equal('get', dispatcher.lookup('no-head', method='HEAD'))

        # replacing handler for one method should not affect others
        self.assert_equal('overriding', dispatcher.lookup('same'))
        self.assert_equal('unaffected', dispatcher.lookup('same', method='POST'))

    def test_accept_dispatch(self):
        dispatcher = d.Dispatcher([
            Binding('test', 'text/json', content_type='text/json'),
            Binding('test', 'text/html', content_type='text/html'),
#            Binding('test', 'catch-all', content_type='*'), TODO
            ])

        # werkzeug accept objects
        self.assert_equal('text/json',
            dispatcher.lookup('test', accept=Accept([('text/json', 1.0)])))
        self.assert_equal('text/html',
            dispatcher.lookup('test', accept=Accept([('text/html', 1.0)])))
# TODO
#        self.assert_equal('text/json',
#            dispatcher.lookup('test', accept=Accept([('application/html', 1.0)])))

        # accept header strings
        self.assert_equal('text/json',
            dispatcher.lookup('test', accept='text/json'))

        self.assert_equal('text/json',
            dispatcher.lookup('test', accept='text/json; q=0.9, text/html; q=0.8'))

    def test_nested(self):
        child = d.Dispatcher([
            Binding('nested', 'Nested'),
            ])
        parent = d.Dispatcher([
            child,
            ])

        self.assert_equal(
            'Nested',
            parent.lookup('nested'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DispatchTestCase))
    return suite
