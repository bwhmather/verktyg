"""
    verktyg.routing
    ~~~~~~~~~~~~~~~

    When it comes to combining multiple controller or view functions (however
    you want to call them) you need a dispatcher.  A simple way would be
    applying regular expression tests on the ``PATH_INFO`` and calling
    registered callback functions that return the value then.

    This module implements a much more powerful system than simple regular
    expression matching because it can also convert values in the URLs and
    build URLs.

    Here a simple example that creates an URLMap for an application with
    two subdomains (www and kb) and some URL rules:

    >>> m = URLMap([
    ...     # Static URLs
    ...     Route('/', endpoint='static/index'),
    ...     Route('/about', endpoint='static/about'),
    ...     Route('/help', endpoint='static/help'),
    ...     # Knowledge Base
    ...     Subdomain('kb', [
    ...         Route('/', endpoint='kb/index'),
    ...         Route('/browse/', endpoint='kb/browse'),
    ...         Route('/browse/<int:id>/', endpoint='kb/browse'),
    ...         Route('/browse/<int:id>/<int:page>', endpoint='kb/browse')
    ...     ])
    ... ], default_subdomain='www')

    If the application doesn't use subdomains it's perfectly fine to not set
    the default subdomain and not use the `Subdomain` route factory.  The
    endpoint in the routes can be anything, for example import paths or unique
    identifiers.  The WSGI application can use those endpoints to get the
    handler for that URL.  It doesn't have to be a string at all but it's
    recommended.

    Now it's possible to create a URL adapter for one of the subdomains and
    build URLs:

    >>> c = m.bind('example.com')
    >>> c.build("kb/browse", dict(id=42))
    'http://kb.example.com/browse/42/'
    >>> c.build("kb/browse", dict())
    'http://kb.example.com/browse/'
    >>> c.build("kb/browse", dict(id=42, page=3))
    'http://kb.example.com/browse/42/3'
    >>> c.build("static/about")
    '/about'
    >>> c.build("static/index", force_external=True)
    'http://www.example.com/'

    >>> c = m.bind('example.com', subdomain='kb')
    >>> c.build("static/about")
    'http://www.example.com/about'

    The first argument to bind is the server name *without* the subdomain.
    Per default it will assume that the script is mounted on the root, but
    often that's not the case so you can provide the real mount point as
    second argument:

    >>> c = m.bind('example.com', '/applications/example')

    The third argument can be the subdomain, if not given the default
    subdomain is used.  For more details about binding have a look at the
    documentation of the `MapAdapter`.

    And here is how you can match URLs:

    >>> c = m.bind('example.com')
    >>> c.match("/")
    ('static/index', {})
    >>> c.match("/about")
    ('static/about', {})
    >>> c = m.bind('example.com', '/', 'kb')
    >>> c.match("/")
    ('kb/index', {})
    >>> c.match("/browse/42/23")
    ('kb/browse', {'id': 42, 'page': 23})

    If matching fails you get a `NotFound` exception, if the route thinks
    it's a good idea to redirect (for example because the URL was defined
    to have a slash at the end but the request was missing that slash) it
    will raise a `RequestRedirect` exception.  Both are subclasses of the
    `HTTPException` so you can use those errors as responses in the
    application.


    :copyright:
        (c) 2014 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import re
import uuid
import posixpath
from urllib.parse import (
    urlencode, quote as urlquote, urljoin,
    urlunparse, ParseResult
)

from pprint import pformat

from werkzeug._internal import _get_environ
from werkzeug._compat import wsgi_decoding_dance

from verktyg.datastructures import ImmutableDict, MultiDict
from verktyg.exceptions import HTTPException, NotFound


_route_re = re.compile(r'''
    (?P<static>[^<]*)                           # static route data
    <
    (?:
        (?P<converter>[a-zA-Z_][a-zA-Z0-9_]*)   # converter name
        (?:\((?P<args>.*?)\))?                  # converter arguments
        \:                                      # variable delimiter
    )?
    (?P<variable>[a-zA-Z_][a-zA-Z0-9_]*)        # variable name
    >
''', re.VERBOSE)
_simple_route_re = re.compile(r'<([^>]+)>')
_converter_args_re = re.compile(r'''
    ((?P<name>\w+)\s*=\s*)?
    (?P<value>
        True|False|
        \d+.\d+|
        \d+.|
        \d+|
        \w+|
        [urUR]?(?P<stringval>"[^"]*?"|'[^']*')
    )\s*,
''', re.VERBOSE | re.UNICODE)


_PYTHON_CONSTANTS = {
    'None':     None,
    'True':     True,
    'False':    False
}


def _pythonize(value):
    if value in _PYTHON_CONSTANTS:
        return _PYTHON_CONSTANTS[value]
    for convert in int, float:
        try:
            return convert(value)
        except ValueError:
            pass
    if value[:1] == value[-1:] and value[0] in '"\'':
        value = value[1:-1]
    return str(value)


def parse_converter_args(argstr):
    argstr += ','
    args = []
    kwargs = {}

    for item in _converter_args_re.finditer(argstr):
        value = item.group('stringval')
        if value is None:
            value = item.group('value')
        value = _pythonize(value)
        if not item.group('name'):
            args.append(value)
        else:
            name = item.group('name')
            kwargs[name] = value

    return tuple(args), kwargs


def parse_route(route):
    """Parse a route and return it as generator. Each iteration yields tuples
    in the form ``(converter, arguments, variable)``. If the converter is
    `None` it's a static url part, otherwise it's a dynamic one.

    :internal:
    """
    pos = 0
    end = len(route)
    do_match = _route_re.match
    used_names = set()
    while pos < end:
        m = do_match(route, pos)
        if m is None:
            break
        data = m.groupdict()
        if data['static']:
            yield None, None, data['static']
        variable = data['variable']
        converter = data['converter'] or 'default'
        if variable in used_names:
            raise ValueError('variable name %r used twice.' % variable)
        used_names.add(variable)
        yield converter, data['args'] or None, variable
        pos = m.end()
    if pos < end:
        remaining = route[pos:]
        if '>' in remaining or '<' in remaining:
            raise ValueError('malformed url rule: %r' % route)
        yield None, None, remaining


class RoutingException(Exception):
    """Special exceptions that require the application to redirect, notifying
    about missing urls, etc.

    :internal:
    """


class RequestRedirect(HTTPException, RoutingException):
    """Raise if the router requests a redirect. This is for example the case if
    `strict_slashes` are activated and an url that requires a trailing slash.

    The attribute `new_url` contains the absolute destination url.
    """
    code = 301

    def __init__(self, new_url):
        RoutingException.__init__(self, new_url)
        self.new_url = new_url


class RequestSlash(RoutingException):
    """Internal exception."""


class RequestAliasRedirect(RoutingException):
    """This route is an alias and wants to redirect to the canonical URL."""

    def __init__(self, matched_values):
        self.matched_values = matched_values


class BuildError(RoutingException, LookupError):
    """Raised if the build system cannot find a URL for an endpoint with the
    values provided.
    """

    def __init__(self, endpoint, values):
        LookupError.__init__(self, endpoint, values)
        self.endpoint = endpoint
        self.values = values


class ValidationError(ValueError):
    """Validation error.  If a route converter raises this exception the route
    does not match the current URL and the next URL is tried.
    """


class RouteFactory(object):
    """As soon as you have more complex URL setups it's a good idea to use route
    factories to avoid repetitive tasks.  Some of them are builtin, others can
    be added by subclassing `RouteFactory` and overriding `get_routes`.
    """

    def get_routes(self, router):
        """Subclasses of `RouteFactory` have to override this method and return
        an iterable of routes."""
        raise NotImplementedError()


class Subdomain(RouteFactory):
    """All URLs provided by this factory have the subdomain set to a
    specific domain. For example if you want to use the subdomain for
    the current language this can be a good setup::

        router = URLMap([
            Route('/', endpoint='#select_language'),
            Subdomain('<string(length=2):lang_code>', [
                Route('/', endpoint='index'),
                Route('/about', endpoint='about'),
                Route('/help', endpoint='help')
            ])
        ])

    All the rules except for the ``'#select_language'`` endpoint will now
    listen on a two letter long subdomain that holds the language code
    for the current request.
    """

    def __init__(self, subdomain, routes):
        self.subdomain = subdomain
        self.routes = routes

    def get_routes(self, router):
        for routefactory in self.routes:
            for route in routefactory.get_routes(router):
                route = route.empty()
                route.subdomain = self.subdomain
                yield route


class Submount(RouteFactory):
    """Like `Subdomain` but prefixes the URL rule with a given string::

        router = URLMap([
            Route('/', endpoint='index'),
            Submount('/blog', [
                Route('/', endpoint='blog/index'),
                Route('/entry/<entry_slug>', endpoint='blog/show')
            ])
        ])

    Now the route ``'blog/show'`` matches ``/blog/entry/<entry_slug>``.
    """

    def __init__(self, path, routes):
        self.path = path.rstrip('/')
        self.routes = routes

    def get_routes(self, router):
        for routefactory in self.routes:
            for route in routefactory.get_routes(router):
                route = route.empty()
                route.route = self.path + route.route
                yield route


class EndpointPrefix(RouteFactory):
    """Prefixes all endpoints (which must be strings for this factory) with
    another string. This can be useful for sub applications::

        router = URLMap([
            Route('/', endpoint='index'),
            EndpointPrefix('blog/', [Submount('/blog', [
                Route('/', endpoint='index'),
                Route('/entry/<entry_slug>', endpoint='show')
            ])])
        ])
    """

    def __init__(self, prefix, routes):
        self.prefix = prefix
        self.routes = routes

    def get_routes(self, router):
        for routefactory in self.routes:
            for route in routefactory.get_routes(router):
                route = route.empty()
                route.endpoint = self.prefix + route.endpoint
                yield route


class RouteTemplate(object):
    """Returns copies of the routes wrapped and expands string templates in
    the endpoint, route, defaults or subdomain sections.

    Here a small example for such a route template::

        from verktyg.routing import URLMap, Route, RouteTemplate

        resource = RouteTemplate([
            Route('/{name}/', endpoint='{name}.list'),
            Route('/{name}/<int:id>', endpoint='{name}.show')
        ])

        router = URLMap([resource(name='user'), resource(name='page')])

    When a route template is called the keyword arguments are used to
    replace the placeholders in all the string parameters.
    """

    def __init__(self, routes):
        self.routes = list(routes)

    def __call__(self, *args, **kwargs):
        return RouteTemplateFactory(self.routes, dict(*args, **kwargs))


class RouteTemplateFactory(RouteFactory):
    """A factory that fills in template variables into routes.  Used by
    `RouteTemplate` internally.

    :internal:
    """

    def __init__(self, routes, context):
        self.routes = routes
        self.context = context

    def get_routes(self, router):
        for routefactory in self.routes:
            for route in routefactory.get_routes(router):
                new_defaults = subdomain = None
                if route.defaults:
                    new_defaults = {}
                    for key, value in route.defaults.items():
                        if isinstance(value, str):
                            value = value.format(**self.context)
                        new_defaults[key] = value
                if route.subdomain is not None:
                    subdomain = route.subdomain.format(**self.context)
                new_endpoint = route.endpoint
                if isinstance(new_endpoint, str):
                    new_endpoint = new_endpoint.format(**self.context)
                yield Route(
                    route.route.format(**self.context),
                    new_defaults,
                    subdomain,
                    route.build_only,
                    new_endpoint,
                    route.strict_slashes
                )


class Route(RouteFactory):
    """A Route represents one URL pattern.  There are some options for `Route`
    that change the way it behaves and are passed to the `Route` constructor.
    Note that besides the route-string all arguments *must* be keyword
    arguments in order to not break the application on Verktyg upgrades.

    `string`
        Route strings basically are just normal URL paths with placeholders in
        the format ``<converter(arguments):name>`` where the converter and the
        arguments are optional.  If no converter is defined the `default`
        converter is used which means `string` in the normal configuration.

        URL routes that end with a slash are branch URLs, others are leaves.
        If you have `strict_slashes` enabled (which is the default), all
        branch URLs that are matched without a trailing slash will trigger a
        redirect to the same URL with the missing slash appended.

        The converters are defined on the `URLMap`.

    `endpoint`
        The endpoint for this route. This can be anything. A reference to a
        function, a string, a number etc.  The preferred way is using a string
        because the endpoint is used for URL generation.

    `defaults`
        An optional dict with defaults for other routes with the same endpoint.
        This is a bit tricky but useful if you want to have unique URLs::

            router = URLMap([
                Route('/all/', defaults={'page': 1}, endpoint='all_entries'),
                Route('/all/page/<int:page>', endpoint='all_entries')
            ])

        If a user now visits ``http://example.com/all/page/1`` he will be
        redirected to ``http://example.com/all/``.  If `redirect_defaults` is
        disabled on the `URLMap` instance this will only affect the URL
        generation.

    `subdomain`
        The subdomain route string for this route. If not specified the route
        only matches for the `default_subdomain` of the router.  If the router
        is not bound to a subdomain this feature is disabled.

        Can be useful if you want to have user profiles on different subdomains
        and all subdomains are forwarded to your application::

            router = URLMap([
                Route('/', subdomain='<username>', endpoint='user/homepage'),
                Route('/stats', subdomain='<username>', endpoint='user/stats')
            ])

    `strict_slashes`
        Override the `URLMap` setting for `strict_slashes` only for this route.
        If not specified the `URLMap` setting is used.

    `build_only`
        Set this to True and the route will never match but will create a URL
        that can be build. This is useful if you have resources on a subdomain
        or folder that are not handled by the WSGI application (like static
        data)

    `redirect_to`
        If given this must be either a string or callable.  In case of a
        callable it's called with the url adapter that triggered the match and
        the values of the URL as keyword arguments and has to return the target
        for the redirect, otherwise it has to be a string with placeholders in
        route syntax::

            def foo_with_slug(adapter, id):
                # ask the database for the slug for the old id.  this of
                # course has nothing to do with verktyg.
                return 'foo/' + Foo.get_slug_for_id(id)

            router = URLMap([
                Route('/foo/<slug>', endpoint='foo'),
                Route('/some/old/url/<slug>', redirect_to='foo/<slug>'),
                Route('/other/old/url/<int:id>', redirect_to=foo_with_slug)
            ])

        When the route is matched the routing system will raise a
        `RequestRedirect` exception with the target for the redirect.

        Keep in mind that the URL will be joined against the URL root of the
        script so don't use a leading slash on the target URL unless you
        really mean root of that domain.

    `alias`
        If enabled this route serves as an alias for another route with the
        same endpoint and arguments.

    `host`
        If provided and the router has host matching enabled this can be
        used to provide a match route for the whole host.  This also means
        that the subdomain feature is disabled.
    """

    def __init__(self, string, defaults=None, subdomain=None,
                 build_only=False, endpoint=None, strict_slashes=None,
                 redirect_to=None, alias=False, host=None):
        if not string.startswith('/'):
            raise ValueError('urls must start with a leading slash')
        self.route = string
        self.is_leaf = not string.endswith('/')

        self.router = None
        self.strict_slashes = strict_slashes
        self.subdomain = subdomain
        self.host = host
        self.defaults = defaults
        self.build_only = build_only
        self.alias = alias
        self.endpoint = endpoint
        self.redirect_to = redirect_to

        if defaults:
            self.arguments = {str(default) for default in defaults}
        else:
            self.arguments = set()
        self._trace = self._converters = self._regex = self._weights = None

    def empty(self):
        """Return an unbound copy of this route.  This can be useful if you
        want to reuse an already bound URL for another router."""
        defaults = None
        if self.defaults:
            defaults = dict(self.defaults)
        return Route(self.route, defaults, self.subdomain,
                     self.build_only, self.endpoint, self.strict_slashes,
                     self.redirect_to, self.alias, self.host)

    def get_routes(self, router):
        yield self

    def refresh(self):
        """Rebinds and refreshes the URL.  Call this if you modified the
        route in place.

        :internal:
        """
        self.bind(self.router, rebind=True)

    def bind(self, router, rebind=False):
        """Bind the url to a router and create a regular expression based on
        the information from the route itself and the defaults from the router.

        :internal:
        """
        if self.router is not None and not rebind:
            raise RuntimeError('url route %r already bound to router %r' %
                               (self, self.router))
        self.router = router
        if self.strict_slashes is None:
            self.strict_slashes = router.strict_slashes
        if self.subdomain is None:
            self.subdomain = router.default_subdomain
        self.compile()

    def get_converter(self, variable_name, converter_name, args, kwargs):
        """Looks up the converter for the given parameter.
        """
        if converter_name not in self.router.converters:
            raise LookupError(
                'the converter %r does not exist' % converter_name
            )
        converter = self.router.converters[converter_name]
        return converter(self.router, *args, **kwargs)

    def compile(self):
        """Compiles the regular expression and stores it."""
        assert self.router is not None, 'route not bound'

        if self.router.host_matching:
            domain_route = self.host or ''
        else:
            domain_route = self.subdomain or ''

        self._trace = []
        self._converters = {}
        self._weights = []
        regex_parts = []

        def _build_regex(route):
            for converter, arguments, variable in parse_route(route):
                if converter is None:
                    regex_parts.append(re.escape(variable))
                    self._trace.append((False, variable))
                    for part in variable.split('/'):
                        if part:
                            self._weights.append((0, -len(part)))
                else:
                    if arguments:
                        c_args, c_kwargs = parse_converter_args(arguments)
                    else:
                        c_args = ()
                        c_kwargs = {}
                    convobj = self.get_converter(
                        variable, converter, c_args, c_kwargs)
                    regex_parts.append(
                        '(?P<%s>%s)' % (variable, convobj.regex)
                    )
                    self._converters[variable] = convobj
                    self._trace.append((True, variable))
                    self._weights.append((1, convobj.weight))
                    self.arguments.add(str(variable))

        _build_regex(domain_route)
        regex_parts.append('\\|')
        self._trace.append((False, '|'))
        _build_regex(self.is_leaf and self.route or self.route.rstrip('/'))
        if not self.is_leaf:
            self._trace.append((False, '/'))

        if self.build_only:
            return
        regex = r'^%s%s$' % (
            u''.join(regex_parts),
            '(?<!/)(?P<__suffix__>/?)'
            if (not self.is_leaf or not self.strict_slashes)
            else ''
        )
        self._regex = re.compile(regex, re.UNICODE)

    def match(self, path):
        """Check if the route matches a given path. Path is a string in the
        form ``"subdomain|/path"`` and is assembled by the router.  If
        the router is doing host matching the subdomain part will be the host
        instead.

        If the route matches a dict with the converted values is returned,
        otherwise the return value is `None`.

        :internal:
        """
        if not self.build_only:
            m = self._regex.search(path)
            if m is not None:
                groups = m.groupdict()
                # we have a folder like part of the url without a trailing
                # slash and strict slashes enabled. raise an exception that
                # tells the router to redirect to the same url but with a
                # trailing slash
                if (
                    self.strict_slashes and not self.is_leaf and
                    not groups.pop('__suffix__')
                ):
                    raise RequestSlash()
                # if we are not in strict slashes mode we have to remove
                # a __suffix__
                elif not self.strict_slashes:
                    del groups['__suffix__']

                result = {}
                for name, value in groups.items():
                    try:
                        value = self._converters[name].to_python(value)
                    except ValidationError:
                        return
                    result[str(name)] = value
                if self.defaults:
                    result.update(self.defaults)

                if self.alias and self.router.redirect_defaults:
                    raise RequestAliasRedirect(result)

                return result

    def build(self, values, append_unknown=True):
        """Assembles the relative url for that route and the subdomain.
        If building doesn't work for some reasons `None` is returned.

        :internal:
        """
        tmp = []
        add = tmp.append
        processed = set(self.arguments)
        for is_dynamic, data in self._trace:
            if is_dynamic:
                try:
                    add(self._converters[data].to_url(values[data]))
                except ValidationError:
                    return
                processed.add(data)
            else:
                add(urlquote(data, encoding=self.router.charset, safe='/:|+'))
        domain_part, url = (u''.join(tmp)).split(u'|', 1)

        if append_unknown:
            query_vars = MultiDict(values)
            for key in processed:
                if key in query_vars:
                    del query_vars[key]

            if query_vars:
                url += u'?' + urlencode(
                    sorted(query_vars.items(), key=self.router.sort_key),
                    encoding=self.router.charset,
                )

        return domain_part, url

    def provides_defaults_for(self, route):
        """Check if this route has defaults for a given route.

        :internal:
        """
        return (
            not self.build_only and self.defaults and
            self.endpoint == route.endpoint and self != route and
            self.arguments == route.arguments
        )

    def suitable_for(self, values):
        """Check if the dict of values has enough data for url generation.

        :internal:
        """
        defaults = self.defaults or ()

        # all arguments required must be either in the defaults dict or
        # the value dictionary otherwise it's not suitable
        for key in self.arguments:
            if key not in defaults and key not in values:
                return False

        # in case defaults are given we ensure that either the value was
        # skipped or the value is the same as the default value.
        if defaults:
            for key, value in defaults.items():
                if key in values and value != values[key]:
                    return False

        return True

    def match_compare_key(self):
        """The match compare key for sorting.

        Current implementation:

        1.  routes without any arguments come first for performance
            reasons only as we expect them to match faster and some
            common ones usually don't have any arguments (index pages etc.)
        2.  The more complex routes come first so the second argument is the
            negative length of the number of weights.
        3.  lastly we order by the actual weights.

        :internal:
        """
        return bool(self.arguments), -len(self._weights), self._weights

    def build_compare_key(self):
        """The build compare key for sorting.

        :internal:
        """
        return (
            self.alias and 1 or 0, -len(self.arguments),
            -len(self.defaults or ())
        )

    def __eq__(self, other):
        return (
            self.__class__ is other.__class__ and
            self._trace == other._trace
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return self.route

    def __repr__(self):
        if self.router is None:
            return u'<%s (unbound)>' % self.__class__.__name__
        tmp = []
        for is_dynamic, data in self._trace:
            if is_dynamic:
                tmp.append(u'<%s>' % data)
            else:
                tmp.append(data)
        return u'<%s %s -> %s>' % (
            self.__class__.__name__,
            repr((u''.join(tmp)).lstrip(u'|')).lstrip(u'u'),
            self.endpoint
        )


class BaseConverter(object):
    """Base class for all converters."""
    regex = '[^/]+'
    weight = 100

    def __init__(self, router):
        self.router = router

    def to_python(self, value):
        return value

    def to_url(self, value):
        if not isinstance(value, (str, bytes)):
            value = str(value)
        return urlquote(value, encoding=self.router.charset, safe='/:')


class UnicodeConverter(BaseConverter):
    """This converter is the default converter and accepts any string but
    only one path segment.  Thus the string can not include a slash.

    This is the default validator.

    Example::

        Route('/pages/<page>'),
        Route('/<string(length=2):lang_code>')

    :param router: the :class:`URLMap`.
    :param minlength: the minimum length of the string.  Must be greater
                      or equal 1.
    :param maxlength: the maximum length of the string.
    :param length: the exact length of the string.
    """

    def __init__(self, router, minlength=1, maxlength=None, length=None):
        BaseConverter.__init__(self, router)
        if length is not None:
            length = '{%d}' % int(length)
        else:
            if maxlength is None:
                maxlength = ''
            else:
                maxlength = int(maxlength)
            length = '{%s,%s}' % (
                int(minlength),
                maxlength
            )
        self.regex = '[^/]' + length


class AnyConverter(BaseConverter):
    """Matches one of the items provided.  Items can either be Python
    identifiers or strings::

        Route('/<any(about, help, imprint, class, "foo,bar"):page_name>')

    :param router: the :class:`URLMap`.
    :param items: this function accepts the possible items as positional
                  arguments.
    """

    def __init__(self, router, *items):
        BaseConverter.__init__(self, router)
        self.regex = '(?:%s)' % '|'.join([re.escape(x) for x in items])


class PathConverter(BaseConverter):
    """Like the default :class:`UnicodeConverter`, but it also matches
    slashes.  This is useful for wikis and similar applications::

        Route('/<path:wikipage>')
        Route('/<path:wikipage>/edit')

    :param router: the :class:`URLMap`.
    """
    regex = '[^/].*?'
    weight = 200


class NumberConverter(BaseConverter):
    """Baseclass for `IntegerConverter` and `FloatConverter`.

    :internal:
    """
    weight = 50

    def __init__(self, router, fixed_digits=0, min=None, max=None):
        BaseConverter.__init__(self, router)
        self.fixed_digits = fixed_digits
        self.min = min
        self.max = max

    def to_python(self, value):
        if (self.fixed_digits and len(value) != self.fixed_digits):
            raise ValidationError()
        value = self.num_convert(value)
        if (
            (self.min is not None and value < self.min) or
            (self.max is not None and value > self.max)
        ):
            raise ValidationError()
        return value

    def to_url(self, value):
        value = self.num_convert(value)
        if self.fixed_digits:
            value = ('%%0%sd' % self.fixed_digits) % value
        return str(value)


class IntegerConverter(NumberConverter):
    """This converter only accepts integer values::

        Route('/page/<int:page>')

    This converter does not support negative values.

    :param router: the :class:`URLMap`.
    :param fixed_digits: the number of fixed digits in the URL.  If you set
                         this to ``4`` for example, the application will
                         only match if the url looks like ``/0001/``.  The
                         default is variable length.
    :param min: the minimal value.
    :param max: the maximal value.
    """
    regex = r'\d+'
    num_convert = int


class FloatConverter(NumberConverter):
    """This converter only accepts floating point values::

        Route('/probability/<float:probability>')

    This converter does not support negative values.

    :param router: the :class:`URLMap`.
    :param min: the minimal value.
    :param max: the maximal value.
    """
    regex = r'\d+\.\d+'
    num_convert = float

    def __init__(self, router, min=None, max=None):
        NumberConverter.__init__(self, router, 0, min, max)


class UUIDConverter(BaseConverter):
    """This converter only accepts UUID strings::

        Route('/object/<uuid:identifier>')

    :param router: the :class:`URLMap`.
    """
    regex = (
        r'[A-Fa-f0-9]{8}-[A-Fa-f0-9]{4}-'
        r'[A-Fa-f0-9]{4}-[A-Fa-f0-9]{4}-[A-Fa-f0-9]{12}'
    )

    def to_python(self, value):
        return uuid.UUID(value)

    def to_url(self, value):
        return str(value)


#: the default converter mapping for the router.
DEFAULT_CONVERTERS = {
    'default':          UnicodeConverter,
    'string':           UnicodeConverter,
    'any':              AnyConverter,
    'path':             PathConverter,
    'int':              IntegerConverter,
    'float':            FloatConverter,
    'uuid':             UUIDConverter,
}


class URLMap(object):
    """The router class stores all the URL rules and some configuration
    parameters.  Some of the configuration values are only stored on the
    `URLMap` instance since those affect all routes, others are just defaults
    and can be overridden for each route.  Note that you have to specify all
    arguments besides the `routes` as keyword arguments!

    :param routes: sequence of url routes for this router.
    :param default_subdomain: The default subdomain for routes without a
                              subdomain defined.
    :param charset: charset of the url. defaults to ``"utf-8"``
    :param strict_slashes: Take care of trailing slashes.
    :param redirect_defaults: This will redirect to the default route if it
                              wasn't visited that way. This helps creating
                              unique URLs.
    :param converters: A dict of converters that adds additional converters
                       to the list of converters. If you redefine one
                       converter this will override the original one.
    :param sort_parameters: If set to `True` the url parameters are sorted.
                            See `urlencode` for more details.
    :param sort_key: The sort key function for `urlencode`.
    :param encoding_errors: the error method to use for decoding
    :param host_matching: if set to `True` it enables the host matching
                          feature and disables the subdomain one.  If
                          enabled the `host` parameter to routes is used
                          instead of the `subdomain` one.
    """

    #:    a dict of default converters to be used.
    default_converters = ImmutableDict(DEFAULT_CONVERTERS)

    def __init__(self, routes=None, default_subdomain='', charset='utf-8',
                 strict_slashes=True, redirect_defaults=True,
                 converters=None, sort_parameters=False, sort_key=None,
                 encoding_errors='replace', host_matching=False):
        self._routes = []
        self._routes_by_endpoint = {}
        self._remap = True

        self.default_subdomain = default_subdomain
        self.charset = charset
        self.encoding_errors = encoding_errors
        self.strict_slashes = strict_slashes
        self.redirect_defaults = redirect_defaults
        self.host_matching = host_matching

        self.converters = self.default_converters.copy()
        if converters:
            self.converters.update(converters)

        self.sort_parameters = sort_parameters
        self.sort_key = sort_key

        self.add_routes(*routes or ())

    def is_endpoint_expecting(self, endpoint, *arguments):
        """Iterate over all routes and check if the endpoint expects
        the arguments provided.  This is for example useful if you have
        some URLs that expect a language code and others that do not and
        you want to wrap the builder a bit so that the current language
        code is automatically added if not provided but endpoints expect
        it.

        :param endpoint: the endpoint to check.
        :param arguments: this function accepts one or more arguments
                          as positional arguments.  Each one of them is
                          checked.
        """
        self.update()
        arguments = set(arguments)
        for route in self._routes_by_endpoint[endpoint]:
            if arguments.issubset(route.arguments):
                return True
        return False

    def iter_routes(self, endpoint=None):
        """Iterate over all routes or the routes of an endpoint.

        :param endpoint: if provided only the routes for that endpoint
                         are returned.
        :return: an iterator
        """
        self.update()
        if endpoint is not None:
            return iter(self._routes_by_endpoint[endpoint])
        return iter(self._routes)

    def add_routes(self, *factories):
        """Add a new route or factory to the router and bind it.  Requires that the
        route is not bound to another router.

        :param routefactory: a :class:`Route` or :class:`RouteFactory`
        """
        for factory in factories:
            for route in factory.get_routes(self):
                route.bind(self)
                self._routes.append(route)
                self._routes_by_endpoint.setdefault(
                    route.endpoint, []
                ).append(route)
        self._remap = True

    def bind(self, server_name, script_name=None, subdomain=None,
             url_scheme='http', path_info=None, query_args=None):
        """Return a new :class:`MapAdapter` with the details specified to the
        call.  Note that `script_name` will default to ``'/'`` if not further
        specified or `None`.  The `server_name` at least is a requirement
        because the HTTP RFC requires absolute URLs for redirects and so all
        redirect exceptions raised by Verktyg will contain the full canonical
        URL.

        If no path_info is passed to :meth:`match` it will use the default path
        info passed to bind.  While this doesn't really make sense for
        manual bind calls, it's useful if you bind a router to a WSGI
        environment which already contains the path info.

        `subdomain` will default to the `default_subdomain` for this router if
        no defined. If there is no `default_subdomain` you cannot use the
        subdomain feature.
        """
        if self.host_matching:
            if subdomain is not None:
                raise RuntimeError('host matching enabled and a '
                                   'subdomain was provided')
        elif subdomain is None:
            subdomain = self.default_subdomain

        if subdomain is not None:
            subdomain = subdomain.lower()
            subdomain = subdomain.encode('idna').decode('ascii')

        if server_name is not None:
            server_name = server_name.lower()
            server_name = server_name.encode('idna').decode('ascii')

        if subdomain and not server_name:
            raise TypeError('subdomain specified without server name')

        if script_name is None:
            script_name = '/'

        return MapAdapter(self, server_name, script_name, subdomain,
                          url_scheme, path_info, query_args)

    def bind_to_environ(self, environ, server_name=None, subdomain=None):
        """Like :meth:`bind` but you can pass it an WSGI environment and it
        will fetch the information from that dictionary.  Note that because of
        limitations in the protocol there is no way to get the current
        subdomain and real `server_name` from the environment.  If you don't
        provide it, Verktyg will use `SERVER_NAME` and `SERVER_PORT` (or
        `HTTP_HOST` if provided) as used `server_name` with disabled subdomain
        feature.

        If `subdomain` is `None` but an environment and a server name is
        provided it will calculate the current subdomain automatically.
        Example: `server_name` is ``'example.com'`` and the `SERVER_NAME`
        in the wsgi `environ` is ``'staging.dev.example.com'`` the calculated
        subdomain will be ``'staging.dev'``.

        If the object passed as environ has an environ attribute, the value of
        this attribute is used instead.  This allows you to pass request
        objects.  Additionally `PATH_INFO` added as a default of the
        :class:`MapAdapter` so that you don't have to pass the path info to
        the match method.

        :param environ: a WSGI environment.
        :param server_name: an optional server name hint (see above).
        :param subdomain: optionally the current subdomain (see above).
        """
        environ = _get_environ(environ)
        if server_name is None:
            if 'HTTP_HOST' in environ:
                server_name = environ['HTTP_HOST']
            else:
                server_name = environ['SERVER_NAME']
                if (
                    (environ['wsgi.url_scheme'], environ['SERVER_PORT']) not
                    in (('https', '443'), ('http', '80'))
                ):
                    server_name += ':' + environ['SERVER_PORT']
        elif subdomain is None and not self.host_matching:
            server_name = server_name.lower()
            if 'HTTP_HOST' in environ:
                wsgi_server_name = environ.get('HTTP_HOST')
            else:
                wsgi_server_name = environ.get('SERVER_NAME')
                if (
                    (environ['wsgi.url_scheme'], environ['SERVER_PORT']) not
                    in (('https', '443'), ('http', '80'))
                ):
                    wsgi_server_name += ':' + environ['SERVER_PORT']
            wsgi_server_name = wsgi_server_name.lower()
            cur_server_name = wsgi_server_name.split('.')
            real_server_name = server_name.split('.')
            offset = -len(real_server_name)
            if cur_server_name[offset:] != real_server_name:
                # This can happen even with valid configs if the server was
                # accesssed directly by IP address under some situations.
                # Instead of raising an exception like in Werkzeug 0.7 or
                # earlier we go by an invalid subdomain which will result
                # in a 404 error on matching.
                subdomain = '<invalid>'
            else:
                subdomain = '.'.join(filter(None, cur_server_name[:offset]))

        def _get_wsgi_string(name):
            val = environ.get(name)
            if val is not None:
                return wsgi_decoding_dance(val, self.charset)

        script_name = _get_wsgi_string('SCRIPT_NAME')
        path_info = _get_wsgi_string('PATH_INFO')
        query_args = _get_wsgi_string('QUERY_STRING')
        return URLMap.bind(self, server_name, script_name,
                           subdomain, environ['wsgi.url_scheme'],
                           path_info, query_args=query_args)

    def update(self):
        """Called before matching and building to keep the compiled routes
        in the correct order after things changed.
        """
        if self._remap:
            self._routes.sort(key=lambda x: x.match_compare_key())
            for routes in self._routes_by_endpoint.values():
                routes.sort(key=lambda x: x.build_compare_key())
            self._remap = False

    def __repr__(self):
        routes = self.iter_routes()
        return '%s(%s)' % (self.__class__.__name__, pformat(list(routes)))


class MapAdapter(object):
    """Returned by :meth:`URLMap.bind` or :meth:`Router.bind_to_environ` and does
    the URL matching and building based on runtime information.
    """

    def __init__(self, router, server_name, script_name, subdomain,
                 url_scheme, path_info, query_args=None):
        self.router = router
        self.server_name = server_name
        script_name = script_name
        if not script_name.endswith(u'/'):
            script_name += u'/'
        self.script_name = script_name
        self.subdomain = subdomain
        self.url_scheme = url_scheme
        self.path_info = path_info
        self.query_args = query_args

    def match(self, path_info=None, return_route=False, query_args=None):
        """The usage is simple: you just pass the match method the current
        path info.  The following things can then happen:

        - you receive a `NotFound` exception that indicates that no URL is
          matching.  A `NotFound` exception is also a WSGI application you
          can call to get a default page not found page (happens to be the
          same object as `verktyg.exceptions.NotFound`)

        - you receive a `RequestRedirect` exception with a `new_url`
          attribute.  This exception is used to notify you about a request
          Werkzeug requests from your WSGI application.  This is for example
          the case if you request ``/foo`` although the correct URL is
          ``/foo/``
          You can use the `RequestRedirect` instance as response-like object
          similar to all other subclasses of `HTTPException`.

        - you get a tuple in the form ``(endpoint, arguments)`` if there is
          a match (unless `return_route` is True, in which case you get a tuple
          in the form ``(route, arguments)``)

        If the path info is not passed to the match method the default path
        info of the map is used (defaults to the root URL if not defined
        explicitly).

        All of the exceptions raised are subclasses of `HTTPException` so they
        can be used as WSGI responses.  The will all render generic error or
        redirect pages.

        Here is a small example for matching:

        >>> m = URLMap([
        ...     Route('/', endpoint='index'),
        ...     Route('/downloads/', endpoint='downloads/index'),
        ...     Route('/downloads/<int:id>', endpoint='downloads/show')
        ... ])
        >>> urls = m.bind("example.com", "/")
        >>> urls.match("/", "GET")
        ('index', {})
        >>> urls.match("/downloads/42")
        ('downloads/show', {'id': 42})

        And here is what happens on redirect and missing URLs:

        >>> urls.match("/downloads")
        Traceback (most recent call last):
          ...
        RequestRedirect: http://example.com/downloads/
        >>> urls.match("/missing")
        Traceback (most recent call last):
          ...
        NotFound: 404 Not Found

        :param path_info: the path info to use for matching.  Overrides the
                          path info specified on binding.
        :param return_route: return the route that matched instead of just the
                            endpoint (defaults to `False`).
        :param query_args: optional query arguments that are used for
                           automatic redirects as string or dictionary.  It's
                           currently not possible to use the query arguments
                           for URL matching.
        """
        self.router.update()
        if path_info is None:
            path_info = self.path_info
        if query_args is None:
            query_args = self.query_args

        path = u'%s|/%s' % (self.router.host_matching and self.server_name or
                            self.subdomain, path_info.lstrip('/'))

        for route in self.router._routes:
            try:
                rv = route.match(path)
            except RequestSlash:
                raise RequestRedirect(self.make_redirect_url(
                    urlquote(
                        path_info, encoding=self.router.charset, safe='/:|+'
                    ) + '/', query_args
                ))
            except RequestAliasRedirect as e:
                raise RequestRedirect(self.make_alias_redirect_url(
                    path, route.endpoint, e.matched_values, query_args
                ))
            if rv is None:
                continue

            if self.router.redirect_defaults:
                redirect_url = self.get_default_redirect(route, rv, query_args)
                if redirect_url is not None:
                    raise RequestRedirect(redirect_url)

            if route.redirect_to is not None:
                if isinstance(route.redirect_to, str):
                    def _handle_match(match):
                        value = rv[match.group(1)]
                        return route._converters[match.group(1)].to_url(value)
                    redirect_url = _simple_route_re.sub(_handle_match,
                                                        route.redirect_to)
                else:
                    redirect_url = route.redirect_to(self, **rv)
                raise RequestRedirect(str(urljoin('%s://%s%s%s' % (
                    self.url_scheme,
                    self.subdomain and self.subdomain + '.' or '',
                    self.server_name,
                    self.script_name
                ), redirect_url)))

            if return_route:
                return route, rv
            else:
                return route.endpoint, rv

        raise NotFound()

    def test(self, path_info=None):
        """Test if a route would match.  Works like `match` but returns `True`
        if the URL matches, or `False` if it does not exist.

        :param path_info: the path info to use for matching.  Overrides the
                          path info specified on binding.
        """
        try:
            self.match(path_info)
        except RequestRedirect:
            pass
        except HTTPException:
            return False
        return True

    def get_host(self, domain_part):
        """Figures out the full host name for the given domain part.  The
        domain part is a subdomain in case host matching is disabled or
        a full host name.
        """
        if self.router.host_matching:
            if domain_part is None:
                return self.server_name
            return domain_part
        subdomain = domain_part
        if subdomain is None:
            subdomain = self.subdomain

        if subdomain:
            return subdomain + '.' + self.server_name

        return self.server_name

    def get_default_redirect(self, route, values, query_args):
        """A helper that returns the URL to redirect to if it finds one.
        This is used for default redirecting only.

        :internal:
        """
        assert self.router.redirect_defaults
        for r in self.router._routes_by_endpoint[route.endpoint]:
            # every route that comes after this one, including ourself
            # has a lower priority for the defaults.  We order the ones
            # with the highest priority up for building.
            if r is route:
                break
            if (
                r.provides_defaults_for(route) and
                r.suitable_for(values)
            ):
                values.update(r.defaults)
                domain_part, path = r.build(values)
                return self.make_redirect_url(
                    path, query_args, domain_part=domain_part)

    def encode_query_args(self, query_args):
        if not isinstance(query_args, str):
            query_args = urlencode(query_args, self.router.charset)
        return query_args

    def make_redirect_url(self, path_info, query_args=None, domain_part=None):
        """Creates a redirect URL.

        :internal:
        """
        return urlunparse(ParseResult(
            scheme=self.url_scheme or '',
            netloc=self.get_host(domain_part),
            path=posixpath.join(
                self.script_name.strip('/'), path_info.lstrip('/')
            ),
            query=self.encode_query_args(query_args) if query_args else '',
            params=None, fragment=None
        ))

    def make_alias_redirect_url(self, path, endpoint, values, query_args):
        """Internally called to make an alias redirect URL."""
        url = self.build(endpoint, values, append_unknown=False,
                         force_external=True)
        if query_args:
            url += '?' + self.encode_query_args(query_args)
        assert url != path, (
            'detected invalid alias setting.  No canonical URL found'
        )
        return url

    def build(self, endpoint, values=None, force_external=False,
              append_unknown=True):
        """Building URLs works pretty much the other way round.  Instead of
        `match` you call `build` and pass it the endpoint and a dict of
        arguments for the placeholders.

        The `build` function also accepts an argument called `force_external`
        which, if you set it to `True` will force external URLs. Per default
        external URLs (include the server name) will only be used if the
        target URL is on a different subdomain.

        >>> m = URLMap([
        ...     Route('/', endpoint='index'),
        ...     Route('/downloads/', endpoint='downloads/index'),
        ...     Route('/downloads/<int:id>', endpoint='downloads/show')
        ... ])
        >>> urls = m.bind("example.com", "/")
        >>> urls.build("index", {})
        '/'
        >>> urls.build("downloads/show", {'id': 42})
        '/downloads/42'
        >>> urls.build("downloads/show", {'id': 42}, force_external=True)
        'http://example.com/downloads/42'

        Because URLs cannot contain non ASCII data you will always get
        bytestrings back.  Non ASCII characters are urlencoded with the
        charset defined on the router instance.

        Additional values are converted to unicode and appended to the URL as
        URL querystring parameters:

        >>> urls.build("index", {'q': 'My Searchstring'})
        '/?q=My+Searchstring'

        If a route does not exist when building a `BuildError` exception is
        raised.

        :param endpoint: the endpoint of the URL to build.
        :param values: the values for the URL to build.  Unhandled values are
                       appended to the URL as query parameters.
        :param force_external: enforce full canonical external URLs.
        :param append_unknown: unknown parameters are appended to the generated
                               URL as query string argument.  Disable this
                               if you want the builder to ignore those.
        """
        self.router.update()
        if values:
            if isinstance(values, MultiDict):
                valueiter = values.iteritems(multi=True)
            else:
                valueiter = values.items()
            values = dict((k, v) for k, v in valueiter if v is not None)
        else:
            values = {}

        rv = None
        for route in self.router._routes_by_endpoint.get(endpoint, ()):
            if route.suitable_for(values):
                rv = route.build(values, append_unknown)
                if rv is not None:
                    break
        if rv is None:
            raise BuildError(endpoint, values)
        domain_part, path = rv

        host = self.get_host(domain_part)

        # shortcut this.
        if not force_external:
            host_matching = self.router.host_matching
            if (
                (host_matching and host == self.server_name) or
                (not host_matching and domain_part == self.subdomain)
            ):
                return str(urljoin(self.script_name, './' + path.lstrip('/')))

        return urlunparse(ParseResult(
            scheme=self.url_scheme or '',
            netloc=host,
            path=posixpath.join(self.script_name, path.lstrip('/')),
            params=None, query=None, fragment=None
        ))
