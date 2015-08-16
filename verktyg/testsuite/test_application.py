"""
    verktyg.testsuite.application
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Tests `Application` utility class.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import unittest

from verktyg.test import Client
from verktyg.exceptions import HTTPException, NotFound, ImATeapot
from verktyg.responses import Response, BaseResponse
from verktyg.views import expose
from verktyg.routing import Route
from verktyg.application import ApplicationBuilder


class ApplicationTestCase(unittest.TestCase):
    def test_basic(self):
        builder = ApplicationBuilder()

        builder.add_routes(Route('/', endpoint='index'))

        @expose(builder, 'index')
        def index(app, request):
            return Response('Hello World')

        app = builder()
        client = Client(app, BaseResponse)

        resp = client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.get_data(), b'Hello World')

    def test_exception_handlers(self):
        builder = ApplicationBuilder()

        @builder.exception_handler(BaseException)
        def default_handler(app, req, exc_type, exc_value, exc_traceback):
            return Response('default handler', status=500)

        @builder.exception_handler(HTTPException)
        def werkzeug_handler(app, req, exc_type, exc_value, exc_traceback):
            return Response('werkzeug handler', exc_value.code)

        @builder.expose(route='/raise_execption')
        def raise_exception(app, req):
            raise Exception()

        @builder.expose(route='/raise_key_error')
        def raise_key_error(app, req):
            raise KeyError()

        @builder.expose(route='/raise_teapot')
        def raise_teapot(app, req):
            raise ImATeapot()

        app = builder()
        client = Client(app, BaseResponse)

        resp = client.get('/raise_execption')
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_data(), b'default handler')

        resp = client.get('/raise_key_error')
        self.assertEqual(resp.status_code, 500)
        self.assertEqual(resp.get_data(), b'default handler')

        resp = client.get('/raise_teapot')
        self.assertEqual(resp.status_code, 418)
        self.assertEqual(resp.get_data(), b'werkzeug handler')

    def test_middleware(self):
        builder = ApplicationBuilder()

        @builder.expose(route='/')
        def index(app, req):
            return Response('Hello')

        got_request = False,
        got_response = False,

        def middleware(app):
            def handler(env, start_response):
                nonlocal got_request
                got_request = True

                def handle_start_response(*args, **kwargs):
                    nonlocal got_response
                    got_response = True
                    return start_response(*args, **kwargs)

                return app(env, handle_start_response)
            return handler

        builder.add_middleware(middleware)

        app = builder()
        client = Client(app, BaseResponse)

        client.get('/')

        self.assertTrue(got_request)
        self.assertTrue(got_response)

    def test_exception_content_type(self):
        builder = ApplicationBuilder()

        @builder.exception_handler(HTTPException)
        def default_handler(app, req, exc_type, exc_value, exc_traceback):
            return Response('default handler', status=exc_value.code)

        @builder.exception_handler(
            HTTPException, content_type='application/json'
        )
        def default_json_handler(app, req, exc_type, exc_value, exc_traceback):
            return Response(
                '{"type": "json"}',
                status=exc_value.code,
                content_type='application/json'
            )

        @builder.exception_handler(NotFound, content_type='text/html')
        def html_not_found_handler(
                app, req, exc_type, exc_value, exc_traceback):
            return Response('pretty NotFound', status=exc_value.code)

        @builder.expose(route='/raise_418')
        def raise_418(app, req):
            raise ImATeapot()

        @builder.expose(route='/raise_404')
        def raise_404(app, req):
            raise NotFound()

        app = builder()
        client = Client(app, BaseResponse)

        resp = client.get('/raise_418')
        self.assertEqual(resp.status_code, 418)
        self.assertEqual(resp.get_data(), b'{"type": "json"}')

        resp = client.get(
            'raise_418', headers=[('Accept', 'application/json')]
        )
        self.assertEqual(resp.status_code, 418)
        self.assertEqual(resp.get_data(), b'{"type": "json"}')

        resp = client.get(
            'raise_418', headers=[('Accept', 'application/xml')]
        )
        self.assertEqual(resp.get_data(), b'default handler')

        # 404 error has a pretty html representation but uses default renderer
        # for json
        resp = client.get('/raise_404', headers=[('Accept', 'text/html')])
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_data(), b'pretty NotFound')

        resp = client.get(
            'raise_404', headers=[('Accept', 'application/json')]
        )
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.get_data(), b'{"type": "json"}')


    def test_close_request(self):
        closed = 0

        class CheckRequestCloseMixin(object):
            def __init__(self):
                def _increment_closed_count():
                    nonlocal closed
                    closed += 1
                self.call_on_close(_increment_closed_count)
                super(CheckRequestCloseMixin, self).__init__()

        builder = ApplicationBuilder()
        builder.add_request_mixins(CheckRequestCloseMixin)

        builder.add_routes(Route('/', endpoint='index'))

        @expose(builder, 'index')
        def index(app, request):
            return Response('Hello World')

        app = builder()
        client = Client(app, BaseResponse)

        # check that requests are closed after success
        client.get('/')
        self.assertEqual(closed, 1)

        # check that requests are closed after an error
        try:
            client.get('/nonexistant')
        except NotFound:
            pass
        self.assertEqual(closed, 2)


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ApplicationTestCase))
    return suite
