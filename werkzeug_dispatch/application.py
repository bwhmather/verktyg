# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.application
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import Request
from werkzeug.routing import Map
from werkzeug.local import Local, LocalManager

from werkzeug_dispatch import Dispatcher


class Application(object):
    """ helper class for creating a wsgi application from a url map and list of
    bindings.

    `url_map`
        werkzeug `Map` object that maps from urls to names

    `dispatcher`
        object to map from endpoint names to handler functions

    """
    def __init__(self, url_map=None, dispatcher=None, request_class=Request):
        """
        :param url_map:
            a werkzeug `Map` object`

        :param dispatcher:
            a `Dispatcher` object

        :param request_class:
            constructor applied to each wsgi environment to create the request
            object to be passed to the handler
        """
        if url_map is None:
            url_map = Map()
        self.url_map = url_map

        if dispatcher is None:
            dispatcher = Dispatcher()
        self.dispatcher = dispatcher

        self._request_class = request_class

        # stack of middleware wrapping :method:`_dispatch_request`. invoked by
        # :method:`__call__`
        self._stack = self._dispatch_request

        # TODO provide a way of adding request specifiv variables.  Need to be
        # able to register name, `(Application, wsgi_env) -> value` pairs
        self._local = Local()
        self._wsgi_env = self._local('wsgi_env')
        self._map_adapter = self._local('map_adapter')

        local_manager = LocalManager([self._local])
        self.add_middleware(local_manager.make_middleware)

    def add_routes(self, *routes):
        for route in routes:
            self.url_map.add(route)

    def add_views(self, *views):
        for view in views:
            self.dispatcher.add(view)

    def add_middleware(self, middleware, *args, **kwargs):
        """ Wrap the application in a layer of wsgi middleware.

        :param middleware:
            a function which takes a wsgi application as it's first argument
            and returns a new wsgi application.  Any other args or kwargs are
            passed after.
        """
        self._stack = middleware(self._stack, *args, **kwargs)

    def _bind(self, wsgi_env):
        self._local.wsgi_env = wsgi_env
        self._local.map_adapter = self.url_map.bind_to_environ(wsgi_env)

    def _dispatch_request(self, wsgi_env, start_response):
        self._bind(wsgi_env)

        def call_view(name, kwargs):
            endpoint = self.dispatcher.lookup(
                name,
                method=wsgi_env.get('REQUEST_METHOD'),
                accept=wsgi_env.get('HTTP_ACCEPT'),
                accept_charset=wsgi_env.get('HTTP_ACCEPT_CHARSET'),
                accept_language=wsgi_env.get('HTTP_ACCEPT_LANGUAGE'))

            request = self._request_class(wsgi_env)

            return endpoint(self, request, **kwargs)

        response = self._map_adapter.dispatch(call_view)

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
