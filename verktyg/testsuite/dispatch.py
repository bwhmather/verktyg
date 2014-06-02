"""
    verktyg.testsuite.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for the core dispatcher.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from werkzeug.testsuite import WerkzeugTestCase

from werkzeug.exceptions import NotImplemented, MethodNotAllowed, NotAcceptable

from verktyg.dispatch import Binding, Dispatcher


class DispatchTestCase(WerkzeugTestCase):
    def test_name_dispatch(self):
        dispatcher = Dispatcher([
            Binding('tweedle-dum', 'Tweedle Dum'),
            Binding('tweedle-dee', 'Tweedle Dee'),
            Binding('same', 'overridden'),
            Binding('same', 'overriding'),
            ])

        self.assert_equal('Tweedle Dum', dispatcher.lookup('tweedle-dum'))
        self.assert_equal('Tweedle Dee', dispatcher.lookup('tweedle-dee'))
        self.assert_raises(NotImplemented, dispatcher.lookup, 'non-existant')
        self.assert_equal('overriding', dispatcher.lookup('same'))

    def test_method_dispatch(self):
        dispatcher = Dispatcher([
            Binding('test', 'get', method='GET'),
            Binding('test', 'post', method='POST'),
            Binding('head', 'head', method='HEAD'),
            Binding('no-head', 'get', method='GET'),
            ])

        # default to 'GET'
        self.assert_equal('get',
                          dispatcher.lookup('test'))
        self.assert_equal('get',
                          dispatcher.lookup('test', method='GET'))

        # `POST` gives something different
        self.assert_equal('post',
                          dispatcher.lookup('test', method='POST'))

        # `PUT` not found
        self.assert_raises(MethodNotAllowed,
                           dispatcher.lookup, 'test', method='PUT')

    def test_head_fallback(self):
        dispatcher = Dispatcher([
            Binding('head', 'head', method='HEAD'),
            Binding('no-head', 'get', method='GET'),
            ])

        # `HEAD` should fall back to `GET`
        self.assert_equal('head',
                          dispatcher.lookup('head', method='HEAD'))
        self.assert_equal('get',
                          dispatcher.lookup('no-head', method='HEAD'))

    def test_method_override(self):
        dispatcher = Dispatcher([
            Binding('same', 'overridden'),
            Binding('same', 'unaffected', method='POST'),
            Binding('same', 'overriding'),
            ])

        # replacing handler for one method should not affect others
        self.assert_equal('overriding',
                          dispatcher.lookup('same'))
        self.assert_equal('unaffected',
                          dispatcher.lookup('same', method='POST'))

    def test_accept_dispatch(self):
        dispatcher = Dispatcher([
            Binding('test', 'text/json', content_type='text/json'),
            Binding('test', 'text/html', content_type='text/html'),
            Binding('test', 'whatever'),
            Binding('nope', 'nope', content_type='application/xml'),
            ])

        # accept header strings
        self.assert_equal(
            'text/json',
            dispatcher.lookup('test', accept='text/json'))

        self.assert_equal(
            'text/json',
            dispatcher.lookup('test',
                              accept='text/json; q=0.9, text/html; q=0.8'))
        self.assert_equal(
            'whatever',
            dispatcher.lookup('test', accept='application/xml'))

        self.assert_raises(
            NotAcceptable,
            dispatcher.lookup, 'nope', accept='text/html')

    def test_nested(self):
        child = Dispatcher([
            Binding('nested', 'Nested'),
            ])
        parent = Dispatcher([
            child,
            ])

        self.assert_equal(
            'Nested',
            parent.lookup('nested'))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DispatchTestCase))
    return suite
