"""
    tests.exceptions
    ~~~~~~~~~~~~~~~~

    The tests for the exception classes.

    :copyright: (c) 2014 by Armin Ronacher.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from verktyg import exceptions


class ExceptionsTestCase(unittest.TestCase):
    def test_aborter_general(self):
        codes = [
            (exceptions.BadRequest, 400),
            (exceptions.Unauthorized, 401),
            (exceptions.Forbidden, 403),
            (exceptions.NotFound, 404),
            (exceptions.MethodNotAllowed, 405, ['GET', 'HEAD']),
            (exceptions.NotAcceptable, 406),
            (exceptions.RequestTimeout, 408),
            (exceptions.Gone, 410),
            (exceptions.LengthRequired, 411),
            (exceptions.PreconditionFailed, 412),
            (exceptions.RequestEntityTooLarge, 413),
            (exceptions.RequestURITooLarge, 414),
            (exceptions.UnsupportedMediaType, 415),
            (exceptions.UnprocessableEntity, 422),
            (exceptions.InternalServerError, 500),
            (exceptions.NotImplemented, 501),
            (exceptions.BadGateway, 502),
            (exceptions.ServiceUnavailable, 503)
        ]
        for exc_type, code, *args in codes:
            with self.subTest(code=code):
                self.assertRaises(exc_type, exceptions.abort, code, *args)

    def test_aborter_custom(self):
        myabort = exceptions.Aborter({1: exceptions.NotFound})
        self.assertRaises(LookupError, myabort, 404)
        self.assertRaises(exceptions.NotFound, myabort, 1)

        myabort = exceptions.Aborter(extra={1: exceptions.NotFound})
        self.assertRaises(exceptions.NotFound, myabort, 404)
        self.assertRaises(exceptions.NotFound, myabort, 1)

    def test_exception_repr(self):
        exc = exceptions.NotFound()
        self.assertEqual(str(exc), '404: Not Found')
        self.assertEqual(repr(exc), "<NotFound '404: Not Found'>")
