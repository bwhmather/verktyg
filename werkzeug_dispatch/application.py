# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.application
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import Request
from werkzeug.routing import Map, Rule
from werkzeug.local import Local, LocalManager
from werkzeug.utils import cached_property

from werkzeug_dispatch.bindings import ExceptionBinding
from werkzeug_dispatch.error_handling import ExceptionHandler
from werkzeug_dispatch.dispatch import Dispatcher
from werkzeug_dispatch.views import expose


class Application(object):
    """ helper class for creating a wsgi application from a url map and list of
    bindings.

    `url_map`
        werkzeug `Map` object that maps from urls to names

    `dispatcher`
        object to map from endpoint names to handler functions

    """

    #: Constructor applied to each wsgi environment to create the request
    #: object to be passed to the handler
    request_class = Request

    @cached_property
    def url_map(self):
        return Map()

    @cached_property
    def dispatcher(self):
        return Dispatcher()

    def __init__(self, debug=False):
        self.debug = debug

        # reference to the bottom of a stack of wsgi middleware wrapping
        # :method:`_dispatch_request`. Invoked by :method:`__call__`.
        # Essentially the real wsgi application.
        self._stack = self._dispatch_request

        # TODO provide a way of adding request specific variables.  Need to be
        # able to register name, `(Application, wsgi_env) -> value` pairs
        # Alternatively get rid of this entirely as it's a massive hack
        self._local = Local()
        self._wsgi_env = self._local('wsgi_env')
        self._map_adapter = self._local('map_adapter')

        local_manager = LocalManager([self._local])
        self.add_middleware(local_manager.make_middleware)

        self._exception_handler = ExceptionHandler()

    def add_routes(self, *routes):
        for route in routes:
            self.url_map.add(route)

    def add_views(self, *views):
        for view in views:
            self.dispatcher.add(view)

    def expose(self, endpoint=None, *args, **kwargs):
        def wrapper(f):
            nonlocal endpoint
            if endpoint is None:
                endpoint = f.__name__

            route = kwargs.pop('route', None)
            if route is not None:
                self.add_routes(Rule(route, endpoint=endpoint))

            return expose(self.dispatcher, endpoint, *args, **kwargs)(f)
        return wrapper

    def add_middleware(self, middleware, *args, **kwargs):
        """ Wrap the application in a layer of wsgi middleware.

        :param middleware:
            a function which takes a wsgi application as it's first argument
            and returns a new wsgi application.  Any other args or kwargs are
            passed after.
        """
        self._stack = middleware(self._stack, *args, **kwargs)

    def add_exception_handler(self, exception_class, handler):
        """ Bind a function to render exceptions of the given class and all
        sub classes.

        Exception handlers take three arguments:
          * a reference to the application
          * a request object
          * the exception to be rendered
        """
        self._exception_handler.add(ExceptionBinding(exception_class, handler))

    def exception_handler(self, exception_class):
        def wrapper(handler):
            self.add_exception_handler(exception_class, handler)
            return handler
        return wrapper

    def _bind(self, wsgi_env):
        self._local.wsgi_env = wsgi_env
        self._local.map_adapter = self.url_map.bind_to_environ(wsgi_env)

    def _dispatch_request(self, wsgi_env, start_response):
        self._bind(wsgi_env)

        request = self.request_class(wsgi_env)

        def call_view(name, kwargs):
            endpoint = self.dispatcher.lookup(
                name,
                method=wsgi_env.get('REQUEST_METHOD'),
                accept=wsgi_env.get('HTTP_ACCEPT'),
                accept_charset=wsgi_env.get('HTTP_ACCEPT_CHARSET'),
                accept_language=wsgi_env.get('HTTP_ACCEPT_LANGUAGE')
            )

            return endpoint(self, request, **kwargs)

        try:
            response = self._map_adapter.dispatch(call_view)
        except BaseException as e:
            # exceptions should be propogated if debug mode is enabled
            if self.debug:
                raise

            handler = self._exception_handler.lookup(
                type(e),
                accept=wsgi_env.get('HTTP_ACCEPT'),
                accept_charset=wsgi_env.get('HTTP_ACCEPT_CHARSET'),
                accept_language=wsgi_env.get('HTTP_ACCEPT_LANGUAGE')
            )
            if handler is None:
                raise
            response = handler(self, request, e)

        return response(wsgi_env, start_response)

    def __call__(self, wsgi_env, start_response):
        return self._stack(wsgi_env, start_response)

    def url_for(self, *args, **kwargs):
        """ construct the url corresponding to an endpoint name and parameters

        Unfortunately will only work if the application has been bound to a
        wsgi request.  If it is not then there is not generally enough
        information to construct full urls.  TODO.
        """
        self._map_adapter(*args, **kwargs)
