"""
    tests.wsgi
    ~~~~~~~~~~

    Tests the WSGI utilities.

    :copyright:
        (c) 2014 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest

from os import path
from io import StringIO, BytesIO
from tempfile import TemporaryDirectory
from contextlib import closing

from werkzeug._compat import to_bytes

from verktyg.test import Client, create_environ, run_wsgi_app
from verktyg.responses import BaseResponse
from verktyg.exceptions import BadRequest, ClientDisconnected
from verktyg import wsgi


class WsgiTestCase(unittest.TestCase):
    def test_shareddatamiddleware_get_file_loader(self):
        app = wsgi.SharedDataMiddleware(None, {})
        self.assertTrue(callable(app.get_file_loader('foo')))

    def test_shared_data_middleware(self):
        def null_application(environ, start_response):
            start_response('404 NOT FOUND', [('Content-Type', 'text/plain')])
            yield b'NOT FOUND'

        with TemporaryDirectory() as test_dir:
            test_file_name = path.join(test_dir, 'äöü').encode()
            with open(test_file_name, 'w') as test_file:
                test_file.write('FOUND')

            app = wsgi.SharedDataMiddleware(null_application, {
                '/':        path.join(path.dirname(__file__), 'resources'),
                '/sources': path.join(path.dirname(__file__), 'resources'),
                '/pkg':     ('werkzeug.debug', 'shared'),
                '/foo':     test_dir
            })

            for p in '/test.txt', '/sources/test.txt', '/foo/äöü':
                with self.subTest(path=p):
                    app_iter, status, headers = run_wsgi_app(
                        app, create_environ(p)
                    )
                    self.assertEqual(status, '200 OK')
                    with closing(app_iter) as app_iter:
                        data = b''.join(app_iter).strip()
                    self.assertEqual(data, b'FOUND')

            app_iter, status, headers = run_wsgi_app(
                app, create_environ('/pkg/debugger.js'))
            with closing(app_iter) as app_iter:
                contents = b''.join(app_iter)
            self.assertIn(b'$(function() {', contents)

            app_iter, status, headers = run_wsgi_app(
                app, create_environ('/missing'))
            self.assertEqual(status, '404 NOT FOUND')
            self.assertEqual(b''.join(app_iter).strip(), b'NOT FOUND')

    def test_dispatchermiddleware(self):
        def null_application(environ, start_response):
            start_response('404 NOT FOUND', [('Content-Type', 'text/plain')])
            yield b'NOT FOUND'

        def dummy_application(environ, start_response):
            start_response('200 OK', [('Content-Type', 'text/plain')])
            yield to_bytes(environ['SCRIPT_NAME'])

        app = wsgi.DispatcherMiddleware(null_application, {
            '/test1': dummy_application,
            '/test2/very': dummy_application,
        })
        tests = {
            '/test1': ('/test1', '/test1/asfd', '/test1/very'),
            '/test2/very': (
                '/test2/very', '/test2/very/long/path/after/script/name'
            ),
        }
        for name, urls in tests.items():
            for p in urls:
                environ = create_environ(p)
                app_iter, status, headers = run_wsgi_app(app, environ)
                self.assertEqual(status, '200 OK')
                self.assertEqual(b''.join(app_iter).strip(), to_bytes(name))

        app_iter, status, headers = run_wsgi_app(
            app, create_environ('/missing'))
        self.assertEqual(status, '404 NOT FOUND')
        self.assertEqual(b''.join(app_iter).strip(), b'NOT FOUND')

    def test_get_host(self):
        env = {
            'HTTP_X_FORWARDED_HOST': 'example.org',
            'SERVER_NAME': 'bullshit', 'HOST_NAME': 'ignore me dammit',
        }
        self.assertEqual(wsgi.get_host(env), 'example.org')
        self.assertEqual(
            wsgi.get_host(create_environ('/', 'http://example.org')),
            'example.org'
        )

    def test_get_host_multiple_forwarded(self):
        env = {
            'HTTP_X_FORWARDED_HOST': 'example.com, example.org',
            'SERVER_NAME': 'bullshit', 'HOST_NAME': 'ignore me dammit',
        }
        self.assertEqual(wsgi.get_host(env), 'example.com')
        self.assertEqual(
            wsgi.get_host(create_environ('/', 'http://example.com')),
            'example.com'
        )

    def test_get_host_validation(self):
        env = {
            'HTTP_X_FORWARDED_HOST': 'example.org',
            'SERVER_NAME': 'bullshit', 'HOST_NAME': 'ignore me dammit',
        }
        self.assertEqual(
            wsgi.get_host(env, trusted_hosts=['.example.org']), 'example.org'
        )
        self.assertRaises(
            BadRequest, wsgi.get_host, env, trusted_hosts=['example.com']
        )

    def test_responder(self):
        def foo(environ, start_response):
            return BaseResponse(b'Test')
        client = Client(wsgi.responder(foo), BaseResponse)
        response = client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(), b'Test')

    def test_pop_path_info(self):
        original_env = {'SCRIPT_NAME': '/foo', 'PATH_INFO': '/a/b///c'}

        # regular path info popping
        def assert_tuple(script_name, path_info):
            self.assertEqual(env.get('SCRIPT_NAME'), script_name)
            self.assertEqual(env.get('PATH_INFO'), path_info)
        env = original_env.copy()

        def pop():
            return wsgi.pop_path_info(env)

        assert_tuple('/foo', '/a/b///c')
        self.assertEqual(pop(), 'a')
        assert_tuple('/foo/a', '/b///c')
        self.assertEqual(pop(), 'b')
        assert_tuple('/foo/a/b', '///c')
        self.assertEqual(pop(), 'c')
        assert_tuple('/foo/a/b///c', '')
        self.assertIsNone(pop())

    def test_peek_path_info(self):
        env = {
            'SCRIPT_NAME': '/foo',
            'PATH_INFO': '/aaa/b///c'
        }

        self.assertEqual(wsgi.peek_path_info(env), 'aaa')
        self.assertEqual(wsgi.peek_path_info(env), 'aaa')
        self.assertEqual(wsgi.peek_path_info(env, charset=None), b'aaa')
        self.assertEqual(wsgi.peek_path_info(env, charset=None), b'aaa')

    def test_path_info_and_script_name_fetching(self):
        env = create_environ('/\N{SNOWMAN}', 'http://example.com/\N{COMET}/')
        self.assertEqual(
            wsgi.get_path_info(env),
            '/\N{SNOWMAN}'
        )
        self.assertEqual(
            wsgi.get_path_info(env, charset=None),
            '/\N{SNOWMAN}'.encode('utf-8')
        )
        self.assertEqual(
            wsgi.get_script_name(env),
            '/\N{COMET}'
        )
        self.assertEqual(
            wsgi.get_script_name(env, charset=None),
            '/\N{COMET}'.encode('utf-8')
        )

    def test_query_string_fetching(self):
        env = create_environ('/?\N{SNOWMAN}=\N{COMET}')
        qs = wsgi.get_query_string(env)
        self.assertEqual(qs, '%E2%98%83=%E2%98%84')

    def test_limited_stream(self):
        class RaisingLimitedStream(wsgi.LimitedStream):
            def on_exhausted(self):
                raise BadRequest('input stream exhausted')

        io = BytesIO(b'123456')
        stream = RaisingLimitedStream(io, 3)
        self.assertEqual(stream.read(), b'123')
        self.assertRaises(BadRequest, stream.read)

        io = BytesIO(b'123456')
        stream = RaisingLimitedStream(io, 3)
        self.assertEqual(stream.tell(), 0)
        self.assertEqual(stream.read(1), b'1')
        self.assertEqual(stream.tell(), 1)
        self.assertEqual(stream.read(1), b'2')
        self.assertEqual(stream.tell(), 2)
        self.assertEqual(stream.read(1), b'3')
        self.assertEqual(stream.tell(), 3)
        self.assertRaises(BadRequest, stream.read)

        io = BytesIO(b'123456\nabcdefg')
        stream = wsgi.LimitedStream(io, 9)
        self.assertEqual(stream.readline(), b'123456\n')
        self.assertEqual(stream.readline(), b'ab')

        io = BytesIO(b'123456\nabcdefg')
        stream = wsgi.LimitedStream(io, 9)
        self.assertEqual(stream.readlines(), [b'123456\n', b'ab'])

        io = BytesIO(b'123456\nabcdefg')
        stream = wsgi.LimitedStream(io, 9)
        self.assertEqual(stream.readlines(2), [b'12'])
        self.assertEqual(stream.readlines(2), [b'34'])
        self.assertEqual(stream.readlines(), [b'56\n', b'ab'])

        io = BytesIO(b'123456\nabcdefg')
        stream = wsgi.LimitedStream(io, 9)
        self.assertEqual(stream.readline(100), b'123456\n')

        io = BytesIO(b'123456\nabcdefg')
        stream = wsgi.LimitedStream(io, 9)
        self.assertEqual(stream.readlines(100), [b'123456\n', b'ab'])

        io = BytesIO(b'123456')
        stream = wsgi.LimitedStream(io, 3)
        self.assertEqual(stream.read(1), b'1')
        self.assertEqual(stream.read(1), b'2')
        self.assertEqual(stream.read(), b'3')
        self.assertEqual(stream.read(), b'')

        io = BytesIO(b'123456')
        stream = wsgi.LimitedStream(io, 3)
        self.assertEqual(stream.read(-1), b'123')

        io = BytesIO(b'123456')
        stream = wsgi.LimitedStream(io, 0)
        self.assertEqual(stream.read(-1), b'')

        io = StringIO('123456')
        stream = wsgi.LimitedStream(io, 0)
        self.assertEqual(stream.read(-1), '')

        io = StringIO('123\n456\n')
        stream = wsgi.LimitedStream(io, 8)
        self.assertEqual(list(stream), ['123\n', '456\n'])

    def test_limited_stream_disconnection(self):
        io = BytesIO(b'A bit of content')

        # disconnect detection on out of bytes
        stream = wsgi.LimitedStream(io, 255)
        self.assertRaises(ClientDisconnected, stream.read)

        # disconnect detection because file close
        io = BytesIO(b'x' * 255)
        io.close()
        stream = wsgi.LimitedStream(io, 255)
        self.assertRaises(ClientDisconnected, stream.read)

    def test_path_info_extraction(self):
        x = wsgi.extract_path_info('http://example.com/app', '/app/hello')
        self.assertEqual(x, '/hello')
        x = wsgi.extract_path_info(
            'http://example.com/app', 'https://example.com/app/hello'
        )
        self.assertEqual(x, '/hello')
        x = wsgi.extract_path_info(
            'http://example.com/app/', 'https://example.com/app/hello'
        )
        self.assertEqual(x, '/hello')
        x = wsgi.extract_path_info('http://example.com/app/',
                                   'https://example.com/app')
        self.assertEqual(x, '/')
        x = wsgi.extract_path_info('http://☃.net/', '/fööbär')
        self.assertEqual(x, '/fööbär')
        x = wsgi.extract_path_info('http://☃.net/x', 'http://☃.net/x/fööbär')
        self.assertEqual(x, '/fööbär')

        env = create_environ('/fööbär', 'http://☃.net/x/')
        x = wsgi.extract_path_info(env, 'http://☃.net/x/fööbär')
        self.assertEqual(x, '/fööbär')

        x = wsgi.extract_path_info('http://example.com/app/',
                                   'https://example.com/a/hello')
        self.assertIsNone(x)
        x = wsgi.extract_path_info('http://example.com/app/',
                                   'https://example.com/app/hello',
                                   collapse_http_schemes=False)
        self.assertIsNone(x)

    def test_get_host_fallback(self):
        self.assertEqual(
            wsgi.get_host({
                'SERVER_NAME':      'foobar.example.com',
                'wsgi.url_scheme':  'http',
                'SERVER_PORT':      '80'
            }),
            'foobar.example.com'
        )
        self.assertEqual(
            wsgi.get_host({
                'SERVER_NAME':      'foobar.example.com',
                'wsgi.url_scheme':  'http',
                'SERVER_PORT':      '81'
            }),
            'foobar.example.com:81'
        )

    def test_get_current_url_unicode(self):
        env = create_environ()
        env['QUERY_STRING'] = 'foo=bar&baz=blah&meh=\xcf'
        rv = wsgi.get_current_url(env)
        self.assertEqual(
            rv, 'http://localhost/?foo=bar&baz=blah&meh=\ufffd'
        )

    def test_multi_part_line_breaks(self):
        data = 'abcdef\r\nghijkl\r\nmnopqrstuvwxyz\r\nABCDEFGHIJK'
        test_stream = StringIO(data)
        lines = list(wsgi.make_line_iter(test_stream, limit=len(data),
                                         buffer_size=16))
        self.assertEqual(
            lines, [
                'abcdef\r\n', 'ghijkl\r\n', 'mnopqrstuvwxyz\r\n', 'ABCDEFGHIJK'
            ]
        )

        data = (
            'abc\r\nThis line is broken by the buffer length.'
            '\r\nFoo bar baz'
        )
        test_stream = StringIO(data)
        lines = list(wsgi.make_line_iter(test_stream, limit=len(data),
                                         buffer_size=24))
        self.assertEqual(
            lines, [
                'abc\r\n',
                'This line is broken by the buffer length.\r\n',
                'Foo bar baz',
            ]
        )

    def test_multi_part_line_breaks_bytes(self):
        data = b'abcdef\r\nghijkl\r\nmnopqrstuvwxyz\r\nABCDEFGHIJK'
        test_stream = BytesIO(data)
        lines = list(wsgi.make_line_iter(test_stream, limit=len(data),
                                         buffer_size=16))
        self.assertEqual(
            lines, [
                b'abcdef\r\n', b'ghijkl\r\n',
                b'mnopqrstuvwxyz\r\n', b'ABCDEFGHIJK'
            ]
        )

        data = (
            b'abc\r\nThis line is broken by the buffer length.'
            b'\r\nFoo bar baz'
        )
        test_stream = BytesIO(data)
        lines = list(wsgi.make_line_iter(test_stream, limit=len(data),
                                         buffer_size=24))
        self.assertEqual(
            lines, [
                b'abc\r\n',
                b'This line is broken by the buffer length.\r\n',
                b'Foo bar baz',
            ]
        )

    def test_multi_part_line_breaks_problematic(self):
        data = 'abc\rdef\r\nghi'
        for x in range(1, 10):
            test_stream = StringIO(data)
            lines = list(wsgi.make_line_iter(test_stream, limit=len(data),
                                             buffer_size=4))
            self.assertEqual(lines, ['abc\r', 'def\r\n', 'ghi'])

    def test_iter_functions_support_iterators(self):
        data = ['abcdef\r\nghi', 'jkl\r\nmnopqrstuvwxyz\r', '\nABCDEFGHIJK']
        lines = list(wsgi.make_line_iter(data))
        self.assertEqual(
            lines, [
                'abcdef\r\n', 'ghijkl\r\n', 'mnopqrstuvwxyz\r\n', 'ABCDEFGHIJK'
            ]
        )

    def test_make_chunk_iter(self):
        data = ['abcdefXghi', 'jklXmnopqrstuvwxyzX', 'ABCDEFGHIJK']
        rv = list(wsgi.make_chunk_iter(data, 'X'))
        self.assertEqual(
            rv, ['abcdef', 'ghijkl', 'mnopqrstuvwxyz', 'ABCDEFGHIJK']
        )

        data = 'abcdefXghijklXmnopqrstuvwxyzXABCDEFGHIJK'
        test_stream = StringIO(data)
        rv = list(wsgi.make_chunk_iter(test_stream, 'X', limit=len(data),
                                       buffer_size=4))
        self.assertEqual(
            rv, ['abcdef', 'ghijkl', 'mnopqrstuvwxyz', 'ABCDEFGHIJK']
        )

    def test_make_chunk_iter_bytes(self):
        data = [b'abcdefXghi', b'jklXmnopqrstuvwxyzX', b'ABCDEFGHIJK']
        rv = list(wsgi.make_chunk_iter(data, b'X'))
        self.assertEqual(
            rv, [b'abcdef', b'ghijkl', b'mnopqrstuvwxyz', b'ABCDEFGHIJK']
        )

        data = b'abcdefXghijklXmnopqrstuvwxyzXABCDEFGHIJK'
        test_stream = BytesIO(data)
        rv = list(wsgi.make_chunk_iter(
            test_stream, b'X', limit=len(data), buffer_size=4)
        )
        self.assertEqual(
            rv, [b'abcdef', b'ghijkl', b'mnopqrstuvwxyz', b'ABCDEFGHIJK']
        )

    def test_lines_longer_buffer_size(self):
        data = '1234567890\n1234567890\n'
        for bufsize in range(1, 15):
            lines = list(wsgi.make_line_iter(
                StringIO(data), limit=len(data), buffer_size=4
            ))
            self.assertEqual(lines, ['1234567890\n', '1234567890\n'])


class EnvironHeadersTestCase(unittest.TestCase):
    def test_basic_interface(self):
        # this happens in multiple WSGI servers because they
        # use a vary naive way to convert the headers;
        broken_env = {
            'HTTP_CONTENT_TYPE':        'text/html',
            'CONTENT_TYPE':             'text/html',
            'HTTP_CONTENT_LENGTH':      '0',
            'CONTENT_LENGTH':           '0',
            'HTTP_ACCEPT':              '*',
            'wsgi.version':             (1, 0)
        }
        headers = wsgi.EnvironHeaders(broken_env)
        self.assertTrue(headers)
        self.assertEqual(len(headers), 3)
        self.assertEqual(sorted(headers), [
            ('Accept', '*'),
            ('Content-Length', '0'),
            ('Content-Type', 'text/html')
        ])
        self.assertFalse(wsgi.EnvironHeaders({'wsgi.version': (1, 0)}))
        self.assertEqual(len(wsgi.EnvironHeaders({'wsgi.version': (1, 0)})), 0)

    def test_return_type_is_unicode(self):
        # environ contains native strings; we return unicode
        headers = wsgi.EnvironHeaders({
            'HTTP_FOO': '\xe2\x9c\x93',
            'CONTENT_TYPE': 'text/plain',
        })
        self.assertEqual(headers['Foo'], u"\xe2\x9c\x93")
        self.assertIsInstance(headers['Foo'], str)
        self.assertIsInstance(headers['Content-Type'], str)
        iter_output = dict(iter(headers))
        self.assertEqual(iter_output['Foo'], u"\xe2\x9c\x93")
        self.assertIsInstance(iter_output['Foo'], str)
        self.assertIsInstance(iter_output['Content-Type'], str)

    def test_bytes_operations(self):
        foo_val = '\xff'
        h = wsgi.EnvironHeaders({
            'HTTP_X_FOO': foo_val
        })

        self.assertEqual(h.get('x-foo', as_bytes=True), b'\xff')
        self.assertEqual(h.get('x-foo'), u'\xff')
