"""
    verktyg.testsuite.routing
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    Routing tests.

    :copyright:
        (c) 2014 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import unittest
import uuid

from verktyg.datastructures import ImmutableDict
from verktyg.test import create_environ
from verktyg import routing as r


class RoutingTestCase(unittest.TestCase):

    def test_basic_routing(self):
        map = r.URLMap([
            r.Route('/', endpoint='index'),
            r.Route('/foo', endpoint='foo'),
            r.Route('/bar/', endpoint='bar')
        ])
        adapter = map.bind('example.org', '/')
        self.assertEqual(
            adapter.match('/'),
            ('index', {})
        )
        self.assertEqual(
            adapter.match('/foo'),
            ('foo', {})
        )
        self.assertEqual(
            adapter.match('/bar/'),
            ('bar', {})
        )
        self.assertRaises(r.RequestRedirect, lambda: adapter.match('/bar'))
        self.assertRaises(r.NotFound, lambda: adapter.match('/blub'))

        adapter = map.bind('example.org', '/test')
        try:
            adapter.match('/bar')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.org/test/bar/')
        else:  # pragma: no cover
            self.fail('Expected request redirect')

        adapter = map.bind('example.org', '/')
        try:
            adapter.match('/bar')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.org/bar/')
        else:  # pragma: no cover
            self.fail('Expected request redirect')

        adapter = map.bind('example.org', '/')
        try:
            adapter.match('/bar', query_args={'aha': 'muhaha'})
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.org/bar/?aha=muhaha')
        else:  # pragma: no cover
            self.fail('Expected request redirect')

        adapter = map.bind('example.org', '/')
        try:
            adapter.match('/bar', query_args='aha=muhaha')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.org/bar/?aha=muhaha')
        else:  # pragma: no cover
            self.fail('Expected request redirect')

        adapter = map.bind_to_environ(create_environ('/bar?foo=bar',
                                                     'http://example.org/'))
        try:
            adapter.match()
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.org/bar/?foo=bar')
        else:  # pragma: no cover
            self.fail('Expected request redirect')

    def test_environ_defaults(self):
        environ = create_environ("/foo")
        self.assertEqual(environ["PATH_INFO"], '/foo')
        m = r.URLMap([
            r.Route("/foo", endpoint="foo"),
            r.Route("/bar", endpoint="bar"),
        ])
        a = m.bind_to_environ(environ)
        self.assertEqual(a.match("/foo"), ('foo', {}))
        self.assertEqual(a.match(), ('foo', {}))
        self.assertEqual(a.match("/bar"), ('bar', {}))
        self.assertRaises(r.NotFound, a.match, "/bars")

    def test_environ_nonascii_pathinfo(self):
        environ = create_environ(u'/лошадь')
        m = r.URLMap([
            r.Route(u'/', endpoint='index'),
            r.Route(u'/лошадь', endpoint='horse')
        ])
        a = m.bind_to_environ(environ)
        self.assertEqual(a.match(u'/'), ('index', {}))
        self.assertEqual(a.match(u'/лошадь'), ('horse', {}))
        self.assertRaises(r.NotFound, a.match, u'/барсук')

    def test_basic_building(self):
        map = r.URLMap([
            r.Route('/', endpoint='index'),
            r.Route('/foo', endpoint='foo'),
            r.Route('/bar/<baz>', endpoint='bar'),
            r.Route('/bar/<int:bazi>', endpoint='bari'),
            r.Route('/bar/<float:bazf>', endpoint='barf'),
            r.Route('/bar/<path:bazp>', endpoint='barp'),
            r.Route('/hehe', endpoint='blah', subdomain='blah')
        ])
        adapter = map.bind('example.org', '/', subdomain='blah')

        self.assertEqual(
            adapter.build('index', {}),
            'http://example.org/'
        )
        self.assertEqual(
            adapter.build('foo', {}),
            'http://example.org/foo'
        )
        self.assertEqual(
            adapter.build('bar', {'baz': 'blub'}),
            'http://example.org/bar/blub'
        )
        self.assertEqual(
            adapter.build('bari', {'bazi': 50}),
            'http://example.org/bar/50'
        )
        self.assertEqual(
            adapter.build('barf', {'bazf': 0.815}),
            'http://example.org/bar/0.815'
        )
        self.assertEqual(
            adapter.build('barp', {'bazp': 'la/di'}),
            'http://example.org/bar/la/di'
        )
        self.assertEqual(
            adapter.build('blah', {}),
            '/hehe'
        )
        self.assertRaises(r.BuildError, lambda: adapter.build('urks'))

        adapter = map.bind('example.org', '/test', subdomain='blah')
        self.assertEqual(
            adapter.build('index', {}),
            'http://example.org/test/'
        )
        self.assertEqual(
            adapter.build('foo', {}),
            'http://example.org/test/foo'
        )
        self.assertEqual(
            adapter.build('bar', {'baz': 'blub'}),
            'http://example.org/test/bar/blub'
        )
        self.assertEqual(
            adapter.build('bari', {'bazi': 50}),
            'http://example.org/test/bar/50'
        )
        self.assertEqual(
            adapter.build('barf', {'bazf': 0.815}),
            'http://example.org/test/bar/0.815'
        )
        self.assertEqual(
            adapter.build('barp', {'bazp': 'la/di'}),
            'http://example.org/test/bar/la/di'
        )
        self.assertEqual(
            adapter.build('blah', {}),
            '/test/hehe'
        )

    def test_defaults(self):
        map = r.URLMap([
            r.Route('/foo/', defaults={'page': 1}, endpoint='foo'),
            r.Route('/foo/<int:page>', endpoint='foo')
        ])
        adapter = map.bind('example.org', '/')

        self.assertEqual(
            adapter.match('/foo/'),
            ('foo', {'page': 1})
        )
        self.assertRaises(r.RequestRedirect, lambda: adapter.match('/foo/1'))
        self.assertEqual(
            adapter.match('/foo/2'),
            ('foo', {'page': 2})
        )
        self.assertEqual(adapter.build('foo', {}), '/foo/')
        self.assertEqual(adapter.build('foo', {'page': 1}), '/foo/')
        self.assertEqual(adapter.build('foo', {'page': 2}), '/foo/2')

    def test_greedy(self):
        map = r.URLMap([
            r.Route('/foo', endpoint='foo'),
            r.Route('/<path:bar>', endpoint='bar'),
            r.Route('/<path:bar>/<path:blub>', endpoint='bar')
        ])
        adapter = map.bind('example.org', '/')

        self.assertEqual(
            adapter.match('/foo'),
            ('foo', {})
        )
        self.assertEqual(
            adapter.match('/blub'),
            ('bar', {'bar': 'blub'})
        )
        self.assertEqual(
            adapter.match('/he/he'),
            ('bar', {'bar': 'he', 'blub': 'he'})
        )

        self.assertEqual(adapter.build('foo', {}), '/foo')
        self.assertEqual(adapter.build('bar', {'bar': 'blub'}), '/blub')
        self.assertEqual(
            adapter.build('bar', {'bar': 'blub', 'blub': 'bar'}),
            '/blub/bar'
        )

    def test_path(self):
        map = r.URLMap([
            r.Route('/', defaults={'name': 'FrontPage'}, endpoint='page'),
            r.Route('/Special', endpoint='special'),
            r.Route('/<int:year>', endpoint='year'),
            r.Route('/<path:name>', endpoint='page'),
            r.Route('/<path:name>/edit', endpoint='editpage'),
            r.Route(
                '/<path:name>/silly/<path:name2>',
                endpoint='sillypage'
            ),
            r.Route(
                '/<path:name>/silly/<path:name2>/edit',
                endpoint='editsillypage'
            ),
            r.Route('/Talk:<path:name>', endpoint='talk'),
            r.Route('/User:<username>', endpoint='user'),
            r.Route('/User:<username>/<path:name>', endpoint='userpage'),
            r.Route('/Files/<path:file>', endpoint='files'),
        ])
        adapter = map.bind('example.org', '/')

        self.assertEqual(
            adapter.match('/'),
            ('page', {'name': 'FrontPage'})
        )
        self.assertRaises(
            r.RequestRedirect,
            adapter.match, '/FrontPage'
        )
        self.assertEqual(
            adapter.match('/Special'),
            ('special', {})
        )
        self.assertEqual(
            adapter.match('/2007'),
            ('year', {'year': 2007})
        )
        self.assertEqual(
            adapter.match('/Some/Page'),
            ('page', {'name': 'Some/Page'})
        )
        self.assertEqual(
            adapter.match('/Some/Page/edit'),
            ('editpage', {'name': 'Some/Page'})
        )
        self.assertEqual(
            adapter.match('/Foo/silly/bar'),
            ('sillypage', {'name': 'Foo', 'name2': 'bar'})
        )
        self.assertEqual(
            adapter.match('/Foo/silly/bar/edit'),
            ('editsillypage', {'name': 'Foo', 'name2': 'bar'})
        )
        self.assertEqual(
            adapter.match('/Talk:Foo/Bar'),
            ('talk', {'name': 'Foo/Bar'})
        )
        self.assertEqual(
            adapter.match('/User:thomas'),
            ('user', {'username': 'thomas'})
        )
        self.assertEqual(
            adapter.match('/User:thomas/projects/werkzeug'),
            ('userpage', {'username': 'thomas', 'name': 'projects/werkzeug'})
        )
        self.assertEqual(
            adapter.match('/Files/downloads/werkzeug/0.2.zip'),
            ('files', {'file': 'downloads/werkzeug/0.2.zip'})
        )

    def test_http_host_before_server_name(self):
        env = {
            'HTTP_HOST':            'wiki.example.com',
            'SERVER_NAME':          'web0.example.com',
            'SERVER_PORT':          '80',
            'SCRIPT_NAME':          '',
            'PATH_INFO':            '',
            'REQUEST_METHOD':       'GET',
            'wsgi.url_scheme':      'http'
        }
        map = r.URLMap([r.Route('/', endpoint='index', subdomain='wiki')])
        adapter = map.bind_to_environ(env, server_name='example.com')
        self.assertEqual(
            adapter.match('/'),
            ('index', {})
        )
        self.assertEqual(
            adapter.build('index', force_external=True),
            'http://wiki.example.com/'
        )
        self.assertEqual(
            adapter.build('index'),
            '/'
        )

        env['HTTP_HOST'] = 'admin.example.com'
        adapter = map.bind_to_environ(env, server_name='example.com')
        self.assertEqual(adapter.build('index'), 'http://wiki.example.com/')

    def test_adapter_url_parameter_sorting(self):
        map = r.URLMap(
            [r.Route('/', endpoint='index')],
            sort_parameters=True,
            sort_key=lambda x: x[1]
        )
        adapter = map.bind('localhost', '/')
        self.assertEqual(
            adapter.build('index', {'x': 20, 'y': 10, 'z': 30},
                          force_external=True),
            'http://localhost/?y=10&x=20&z=30'
        )

    def test_request_direct_charset_bug(self):
        map = r.URLMap([r.Route(u'/öäü/')])
        adapter = map.bind('localhost', '/')
        try:
            adapter.match(u'/öäü')
        except r.RequestRedirect as e:
            self.assertEqual(
                e.new_url,
                'http://localhost/%C3%B6%C3%A4%C3%BC/'
            )
        else:  # pragma: no cover
            self.fail('expected request redirect exception')

    def test_request_redirect_default(self):
        map = r.URLMap([
            r.Route(u'/foo', defaults={'bar': 42}),
            r.Route(u'/foo/<int:bar>'),
        ])
        adapter = map.bind('localhost', '/')
        try:
            adapter.match(u'/foo/42')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://localhost/foo')
        else:  # pragma: no cover
            self.fail('expected request redirect exception')

    def test_request_redirect_default_subdomain(self):
        map = r.URLMap([
            r.Route(u'/foo', defaults={'bar': 42}, subdomain='test'),
            r.Route(u'/foo/<int:bar>', subdomain='other'),
        ])
        adapter = map.bind('localhost', '/', subdomain='other')
        try:
            adapter.match(u'/foo/42')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://test.localhost/foo')
        else:  # pragma: no cover
            self.fail('expected request redirect exception')

    def test_adapter_match_return_route(self):
        route = r.Route('/foo/', endpoint='foo')
        map = r.URLMap([route])
        adapter = map.bind('localhost', '/')
        self.assertEqual(
            adapter.match('/foo/', return_route=True),
            (route, {})
        )

    def test_server_name_interpolation(self):
        server_name = 'example.invalid'
        map = r.URLMap([
            r.Route('/', endpoint='index'),
            r.Route('/', endpoint='alt', subdomain='alt'),
        ])

        env = create_environ('/', 'http://%s/' % server_name)
        adapter = map.bind_to_environ(env, server_name=server_name)
        self.assertEqual(
            adapter.match(),
            ('index', {})
        )

        env = create_environ('/', 'http://alt.%s/' % server_name)
        adapter = map.bind_to_environ(env, server_name=server_name)
        self.assertEqual(
            adapter.match(),
            ('alt', {})
        )

        env = create_environ('/', 'http://%s/' % server_name)
        adapter = map.bind_to_environ(env, server_name='foo')
        self.assertEqual(adapter.subdomain, '<invalid>')

    def test_route_templates(self):
        testcase = r.RouteTemplate([
            r.Submount('/test/$app', [
                r.Route('/foo/', endpoint='handle_foo'),
                r.Route('/bar/', endpoint='handle_bar'),
                r.Route('/baz/', endpoint='handle_baz'),
            ]),
            r.EndpointPrefix('${app}', [
                r.Route('/${app}-blah', endpoint='bar'),
                r.Route('/${app}-meh', endpoint='baz'),
            ]),
            r.Subdomain('$app', [
                r.Route('/blah', endpoint='x_bar'),
                r.Route('/meh', endpoint='x_baz'),
            ])
        ])

        url_map = r.URLMap([
            testcase(app='test1'),
            testcase(app='test2'),
            testcase(app='test3'),
            testcase(app='test4'),
        ])

        out = sorted([(x.route, x.subdomain, x.endpoint)
                      for x in url_map.iter_routes()])

        self.assertEqual(out, [
            ('/blah', 'test1', 'x_bar'),
            ('/blah', 'test2', 'x_bar'),
            ('/blah', 'test3', 'x_bar'),
            ('/blah', 'test4', 'x_bar'),
            ('/meh', 'test1', 'x_baz'),
            ('/meh', 'test2', 'x_baz'),
            ('/meh', 'test3', 'x_baz'),
            ('/meh', 'test4', 'x_baz'),
            ('/test/test1/bar/', '', 'handle_bar'),
            ('/test/test1/baz/', '', 'handle_baz'),
            ('/test/test1/foo/', '', 'handle_foo'),
            ('/test/test2/bar/', '', 'handle_bar'),
            ('/test/test2/baz/', '', 'handle_baz'),
            ('/test/test2/foo/', '', 'handle_foo'),
            ('/test/test3/bar/', '', 'handle_bar'),
            ('/test/test3/baz/', '', 'handle_baz'),
            ('/test/test3/foo/', '', 'handle_foo'),
            ('/test/test4/bar/', '', 'handle_bar'),
            ('/test/test4/baz/', '', 'handle_baz'),
            ('/test/test4/foo/', '', 'handle_foo'),
            ('/test1-blah', '', 'test1bar'),
            ('/test1-meh', '', 'test1baz'),
            ('/test2-blah', '', 'test2bar'),
            ('/test2-meh', '', 'test2baz'),
            ('/test3-blah', '', 'test3bar'),
            ('/test3-meh', '', 'test3baz'),
            ('/test4-blah', '', 'test4bar'),
            ('/test4-meh', '', 'test4baz')
        ])

    def test_non_string_parts(self):
        m = r.URLMap([
            r.Route('/<foo>', endpoint='foo')
        ])
        a = m.bind('example.com')
        self.assertEqual(a.build('foo', {'foo': 42}), '/42')

    def test_complex_routing_routes(self):
        m = r.URLMap([
            r.Route('/', endpoint='index'),
            r.Route('/<int:blub>', endpoint='an_int'),
            r.Route('/<blub>', endpoint='a_string'),
            r.Route('/foo/', endpoint='nested'),
            r.Route('/foobar/', endpoint='nestedbar'),
            r.Route('/foo/<path:testing>/', endpoint='nested_show'),
            r.Route('/foo/<path:testing>/edit', endpoint='nested_edit'),
            r.Route('/users/', endpoint='users', defaults={'page': 1}),
            r.Route('/users/page/<int:page>', endpoint='users'),
            r.Route('/foox', endpoint='foox'),
            r.Route('/<path:bar>/<path:blub>', endpoint='barx_path_path')
        ])
        a = m.bind('example.com')

        self.assertEqual(
            a.match('/'),
            ('index', {})
        )
        self.assertEqual(
            a.match('/42'),
            ('an_int', {'blub': 42})
        )
        self.assertEqual(
            a.match('/blub'),
            ('a_string', {'blub': 'blub'})
        )
        self.assertEqual(
            a.match('/foo/'),
            ('nested', {})
        )
        self.assertEqual(
            a.match('/foobar/'),
            ('nestedbar', {})
        )
        self.assertEqual(
            a.match('/foo/1/2/3/'),
            ('nested_show', {'testing': '1/2/3'})
        )
        self.assertEqual(
            a.match('/foo/1/2/3/edit'),
            ('nested_edit', {'testing': '1/2/3'})
        )
        self.assertEqual(
            a.match('/users/'),
            ('users', {'page': 1})
        )
        self.assertEqual(
            a.match('/users/page/2'),
            ('users', {'page': 2})
        )
        self.assertEqual(
            a.match('/foox'),
            ('foox', {})
        )
        self.assertEqual(
            a.match('/1/2/3'),
            ('barx_path_path', {'bar': '1', 'blub': '2/3'})
        )

        self.assertEqual(
            a.build('index'),
            '/'
        )
        self.assertEqual(
            a.build('an_int', {'blub': 42}),
            '/42'
        )
        self.assertEqual(
            a.build('a_string', {'blub': 'test'}),
            '/test'
        )
        self.assertEqual(
            a.build('nested'),
            '/foo/'
        )
        self.assertEqual(
            a.build('nestedbar'),
            '/foobar/'
        )
        self.assertEqual(
            a.build('nested_show', {'testing': '1/2/3'}),
            '/foo/1/2/3/'
        )
        self.assertEqual(
            a.build('nested_edit', {'testing': '1/2/3'}),
            '/foo/1/2/3/edit'
        )
        self.assertEqual(
            a.build('users', {'page': 1}),
            '/users/'
        )
        self.assertEqual(
            a.build('users', {'page': 2}),
            '/users/page/2'
        )
        self.assertEqual(
            a.build('foox'),
            '/foox'
        )
        self.assertEqual(
            a.build('barx_path_path', {'bar': '1', 'blub': '2/3'}),
            '/1/2/3'
        )

    def test_default_converters(self):
        class MyURLMap(r.URLMap):
            default_converters = r.URLMap.default_converters.copy()
            default_converters['foo'] = r.UnicodeConverter
        assert isinstance(r.URLMap.default_converters, ImmutableDict)
        m = MyURLMap([
            r.Route('/a/<foo:a>', endpoint='a'),
            r.Route('/b/<foo:b>', endpoint='b'),
            r.Route('/c/<c>', endpoint='c')
        ], converters={'bar': r.UnicodeConverter})
        a = m.bind('example.org', '/')
        self.assertEqual(a.match('/a/1'), ('a', {'a': '1'}))
        self.assertEqual(a.match('/b/2'), ('b', {'b': '2'}))
        self.assertEqual(a.match('/c/3'), ('c', {'c': '3'}))
        assert 'foo' not in r.URLMap.default_converters

    def test_uuid_converter(self):
        m = r.URLMap([
            r.Route('/a/<uuid:a_uuid>', endpoint='a')
        ])
        a = m.bind('example.org', '/')
        rooute, kwargs = a.match('/a/a8098c1a-f86e-11da-bd1a-00112444be1e')
        self.assertEqual(type(kwargs['a_uuid']), uuid.UUID)

    def test_build_append_unknown(self):
        map = r.URLMap([
            r.Route('/bar/<float:bazf>', endpoint='barf')
        ])
        adapter = map.bind('example.org', '/', subdomain='blah')
        self.assertEqual(
            adapter.build('barf', {'bazf': 0.815, 'bif': 1.0}),
            'http://example.org/bar/0.815?bif=1.0'
        )
        self.assertEqual(
            adapter.build('barf', {'bazf': 0.815, 'bif': 1.0},
                          append_unknown=False),
            'http://example.org/bar/0.815'
        )

    def test_protocol_joining_bug(self):
        m = r.URLMap([r.Route('/<foo>', endpoint='x')])
        a = m.bind('example.org')
        self.assertEqual(a.build('x', {'foo': 'x:y'}), '/x:y')
        self.assertEqual(
            a.build('x', {'foo': 'x:y'}, force_external=True),
            'http://example.org/x:y'
        )

    def test_external_building_with_port(self):
        map = r.URLMap([
            r.Route('/', endpoint='index'),
        ])
        adapter = map.bind('example.org:5000', '/')
        built_url = adapter.build('index', {}, force_external=True)
        self.assertEqual(built_url, 'http://example.org:5000/', built_url)

    def test_external_building_with_port_bind_to_environ(self):
        map = r.URLMap([
            r.Route('/', endpoint='index'),
        ])
        adapter = map.bind_to_environ(
            create_environ('/', 'http://example.org:5000/'),
            server_name="example.org:5000"
        )
        built_url = adapter.build('index', {}, force_external=True)
        self.assertEqual(built_url, 'http://example.org:5000/', built_url)

    def test_external_building_with_port_bind_to_environ_bad_servername(self):
        map = r.URLMap([
            r.Route('/', endpoint='index'),
        ])
        environ = create_environ('/', 'http://example.org:5000/')
        adapter = map.bind_to_environ(environ, server_name="example.org")
        self.assertEqual(adapter.subdomain, '<invalid>')

    def test_converter_parser(self):
        args, kwargs = r.parse_converter_args(u'test, a=1, b=3.0')

        self.assertEqual(args, ('test',))
        self.assertEqual(kwargs, {'a': 1, 'b': 3.0})

        args, kwargs = r.parse_converter_args('')
        assert not args and not kwargs

        args, kwargs = r.parse_converter_args('a, b, c,')
        self.assertEqual(args, ('a', 'b', 'c'))
        assert not kwargs

        args, kwargs = r.parse_converter_args('True, False, None')
        self.assertEqual(args, (True, False, None))

        args, kwargs = r.parse_converter_args('"foo", u"bar"')
        self.assertEqual(args, ('foo', 'bar'))

    def test_alias_redirects(self):
        m = r.URLMap([
            r.Route('/', endpoint='index'),
            r.Route('/index.html', endpoint='index', alias=True),
            r.Route('/users/', defaults={'page': 1}, endpoint='users'),
            r.Route('/users/index.html', defaults={'page': 1}, alias=True,
                    endpoint='users'),
            r.Route('/users/page/<int:page>', endpoint='users'),
            r.Route('/users/page-<int:page>.html', alias=True,
                    endpoint='users'),
        ])
        a = m.bind('example.com')

        def ensure_redirect(path, new_url, args=None):
            try:
                a.match(path, query_args=args)
            except r.RequestRedirect as e:
                self.assertEqual(e.new_url, 'http://example.com' + new_url)
            else:  # pragma: no cover
                self.fail('expected redirect')

        ensure_redirect('/index.html', '/')
        ensure_redirect('/users/index.html', '/users/')
        ensure_redirect('/users/page-2.html', '/users/page/2')
        ensure_redirect('/users/page-1.html', '/users/')
        ensure_redirect('/users/page-1.html', '/users/?foo=bar',
                        {'foo': 'bar'})

        self.assertEqual(a.build('index'), '/')
        self.assertEqual(a.build('users', {'page': 1}), '/users/')
        self.assertEqual(a.build('users', {'page': 2}), '/users/page/2')

    def test_double_defaults(self):
        for prefix in '', '/aaa':
            m = r.URLMap([
                r.Route(
                    prefix + '/',
                    defaults={'foo': 1, 'bar': False},
                    endpoint='x'
                ),
                r.Route(
                    prefix + '/<int:foo>',
                    defaults={'bar': False},
                    endpoint='x'
                ),
                r.Route(
                    prefix + '/bar/',
                    defaults={'foo': 1, 'bar': True},
                    endpoint='x'
                ),
                r.Route(
                    prefix + '/bar/<int:foo>',
                    defaults={'bar': True},
                    endpoint='x'
                ),
            ])
            a = m.bind('example.com')

            self.assertEqual(
                a.match(prefix + '/'),
                ('x', {'foo': 1, 'bar': False})
            )
            self.assertEqual(
                a.match(prefix + '/2'),
                ('x', {'foo': 2, 'bar': False})
            )
            self.assertEqual(
                a.match(prefix + '/bar/'),
                ('x', {'foo': 1, 'bar': True})
            )
            self.assertEqual(
                a.match(prefix + '/bar/2'),
                ('x', {'foo': 2, 'bar': True})
            )

            self.assertEqual(
                a.build('x', {'foo': 1, 'bar': False}),
                prefix + '/'
            )
            self.assertEqual(
                a.build('x', {'foo': 2, 'bar': False}),
                prefix + '/2'
            )
            self.assertEqual(
                a.build('x', {'bar': False}),
                prefix + '/'
            )
            self.assertEqual(
                a.build('x', {'foo': 1, 'bar': True}),
                prefix + '/bar/'
            )
            self.assertEqual(
                a.build('x', {'foo': 2, 'bar': True}),
                prefix + '/bar/2'
            )
            self.assertEqual(
                a.build('x', {'bar': True}),
                prefix + '/bar/'
            )

    def test_host_matching(self):
        m = r.URLMap([
            r.Route(
                '/',
                endpoint='index',
                host='www.<domain>'
            ),
            r.Route(
                '/',
                endpoint='files',
                host='files.<domain>'
            ),
            r.Route(
                '/foo/',
                defaults={'page': 1},
                host='www.<domain>',
                endpoint='x'
            ),
            r.Route(
                '/<int:page>',
                host='files.<domain>',
                endpoint='x'
            )
        ], host_matching=True)

        a = m.bind('www.example.com')
        self.assertEqual(
            a.match('/'),
            ('index', {'domain': 'example.com'})
        )
        self.assertEqual(
            a.match('/foo/'),
            ('x', {'domain': 'example.com', 'page': 1})
        )
        try:
            a.match('/foo')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://www.example.com/foo/')
        else:  # pragma: no cover
            self.fail('expected redirect')

        a = m.bind('files.example.com')
        self.assertEqual(
            a.match('/'),
            ('files', {'domain': 'example.com'})
        )
        self.assertEqual(
            a.match('/2'),
            ('x', {'domain': 'example.com', 'page': 2})
        )
        try:
            a.match('/1')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://www.example.com/foo/')
        else:  # pragma: no cover
            self.fail('expected redirect')

    def test_server_name_casing(self):
        m = r.URLMap([
            r.Route('/', endpoint='index', subdomain='foo')
        ])

        env = create_environ()
        env['SERVER_NAME'] = env['HTTP_HOST'] = 'FOO.EXAMPLE.COM'
        a = m.bind_to_environ(env, server_name='example.com')
        self.assertEqual(a.match('/'), ('index', {}))

        env = create_environ()
        env['SERVER_NAME'] = '127.0.0.1'
        env['SERVER_PORT'] = '5000'
        del env['HTTP_HOST']
        a = m.bind_to_environ(env, server_name='example.com')
        try:
            a.match()
        except r.NotFound:
            pass
        else:  # pragma: no cover
            self.fail('Expected not found exception')

    def test_redirect_path_quoting(self):
        url_map = r.URLMap([
            r.Route('/<category>', defaults={'page': 1}, endpoint='category'),
            r.Route('/<category>/page/<int:page>', endpoint='category')
        ])

        adapter = url_map.bind('example.com')
        try:
            adapter.match('/foo bar/page/1')
        except r.RequestRedirect as e:
            self.assertEqual(e.new_url, 'http://example.com/foo%20bar')
        else:  # pragma: no cover
            self.fail('Expected redirect')

    def test_unicode_routes(self):
        m = r.URLMap([
            r.Route(u'/войти/', endpoint='enter'),
            r.Route(u'/foo+bar/', endpoint='foobar')
        ])
        a = m.bind(u'☃.example.com')
        try:
            a.match(u'/войти')
        except r.RequestRedirect as e:
            self.assertEqual(
                e.new_url,
                'http://xn--n3h.example.com/%D0%B2%D0%BE%D0%B9%D1%82%D0%B8/'
            )
        endpoint, values = a.match(u'/войти/')
        self.assertEqual(endpoint, 'enter')
        self.assertEqual(values, {})

        try:
            a.match(u'/foo+bar')
        except r.RequestRedirect as e:
            self.assertEqual(
                e.new_url,
                'http://xn--n3h.example.com/foo+bar/'
            )
        endpoint, values = a.match(u'/foo+bar/')
        self.assertEqual(endpoint, 'foobar')
        self.assertEqual(values, {})

        url = a.build('enter', {}, force_external=True)
        self.assertEqual(
            url,
            'http://xn--n3h.example.com/%D0%B2%D0%BE%D0%B9%D1%82%D0%B8/'
        )

        url = a.build('foobar', {}, force_external=True)
        self.assertEqual(url, 'http://xn--n3h.example.com/foo+bar/')

    def test_map_repr(self):
        m = r.URLMap([
            r.Route(u'/wat', endpoint='enter'),
            r.Route(u'/woop', endpoint='foobar')
        ])
        rv = repr(m)
        self.assertEqual(
            rv,
            "URLMap([<Route '/woop' -> foobar>, <Route '/wat' -> enter>])"
        )


def suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(RoutingTestCase))
    return suite
