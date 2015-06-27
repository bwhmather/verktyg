"""
    verktyg.testsuite.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests for the core dispatcher.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from verktyg.exceptions import NotImplemented, MethodNotAllowed, NotAcceptable
from verktyg.dispatch import Binding, Dispatcher


def _make_view(value):
    def view(app, req):
        return value
    return view


class DispatchTestCase(unittest.TestCase):
    def test_name_dispatch(self):
        dispatcher = Dispatcher([
            Binding('tweedle-dum', _make_view('Tweedle Dum')),
            Binding('tweedle-dee', _make_view('Tweedle Dee')),
            Binding('same', _make_view('overridden')),
            Binding('same', _make_view('overriding')),
        ])

        self.assertEqual(
            'Tweedle Dum', dispatcher.lookup('tweedle-dum')(None, None)
        )
        self.assertEqual(
            'Tweedle Dee', dispatcher.lookup('tweedle-dee')(None, None)
        )
        self.assertRaises(NotImplemented, dispatcher.lookup, 'non-existant')
        self.assertEqual(
            'overriding', dispatcher.lookup('same')(None, None)
        )

    def test_method_dispatch(self):
        dispatcher = Dispatcher([
            Binding('test', _make_view('get'), method='GET'),
            Binding('test', _make_view('post'), method='POST'),
            Binding('head', _make_view('head'), method='HEAD'),
            Binding('no-head', _make_view('get'), method='GET'),
        ])

        # default to 'GET'
        self.assertEqual(
            'get', dispatcher.lookup('test')(None, None)
        )
        self.assertEqual(
            'get', dispatcher.lookup('test', method='GET')(None, None)
        )

        # `POST` gives something different
        self.assertEqual(
            'post', dispatcher.lookup('test', method='POST')(None, None)
        )

        # `PUT` not found
        self.assertRaises(
            MethodNotAllowed, dispatcher.lookup, 'test', method='PUT'
        )

    def test_head_fallback(self):
        dispatcher = Dispatcher([
            Binding('head', _make_view('head'), method='HEAD'),
            Binding('no-head', _make_view('get'), method='GET'),
        ])

        # `HEAD` should fall back to `GET`
        self.assertEqual(
            'head', dispatcher.lookup('head', method='HEAD')(None, None)
        )
        self.assertEqual(
            'get', dispatcher.lookup('no-head', method='HEAD')(None, None)
        )

    def test_method_override(self):
        dispatcher = Dispatcher([
            Binding('same', _make_view('overridden')),
            Binding('same', _make_view('unaffected'), method='POST'),
            Binding('same', _make_view('overriding')),
        ])

        # replacing handler for one method should not affect others
        self.assertEqual(
            'overriding', dispatcher.lookup('same')(None, None)
        )
        self.assertEqual(
            'unaffected', dispatcher.lookup('same', method='POST')(None, None)
        )

    def test_accept_dispatch(self):
        dispatcher = Dispatcher([
            Binding(
                'test', _make_view('json'),
                content_type='application/json'
            ),
            Binding(
                'test', _make_view('html'),
                content_type='text/html'
            ),
            Binding(
                'test', _make_view('whatever')
            ),
            Binding(
                'nope', _make_view('nope'),
                content_type='application/xml'
            ),
        ])

        # accept header strings
        self.assertEqual(
            'json',
            dispatcher.lookup('test', accept='application/json')(None, None)
        )

        self.assertEqual(
            'json',
            dispatcher.lookup(
                'test', accept='application/json; q=0.9, text/html; q=0.8'
            )(None, None)
        )
        self.assertEqual(
            'whatever',
            dispatcher.lookup('test', accept='application/xml')(None, None)
        )

        self.assertRaises(
            NotAcceptable,
            dispatcher.lookup, 'nope', accept='text/html'
        )

    def test_nested(self):
        child = Dispatcher([
            Binding('nested', _make_view('Nested')),
            ])
        parent = Dispatcher([
            child,
            ])

        self.assertEqual(
            'Nested',
            parent.lookup('nested')(None, None))


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(DispatchTestCase))
    return suite
