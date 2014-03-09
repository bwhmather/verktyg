# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.application
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import Request
from werkzeug.local import Local, LocalManager


class Application(object):
    """
    `url_map`
        werkzeug `Map` object that maps from urls to names

    `dispatcher`
        object to map from endpoint names to handler functions

    """
    def __init__(self, url_map, dispatcher, request_class=Request):
        """
        :param url_map:
            a werkzeug `Map` object`

        :param dispatcher:
            a `Dispatcher` object

        :param request_class:
            constructor applied to each wsgi environment to create the request
            object to be passed to the handler
        """
        self.url_map = url_map
        self.dispatcher = dispatcher
        self._request_class = request_class

        self._local = Local()
        self._wsgi_env = self._local('wsgi_env')
        self._map_adapter = self._local('map_adapter')

        local_manager = LocalManager([self._local])
        self._dispatch = local_manager.make_middleware(self._dispatch_request)

    def _bind(self, wsgi_env):
        self._local.wsgi_env = wsgi_env
        self._local.map_adapter = self.url_map.bind_to_environ(wsgi_env)

    def _dispatch_request(self, wsgi_env, start_response):
        self._bind(wsgi_env)

        def call_view(name, kwargs):
            request = self._request_class(wsgi_env)

            endpoint = self.dispatcher.lookup(
                name, method=request.method,
                accept=wsgi_env.get('HTTP_ACCEPT'),
                accept_charset=wsgi_env.get('HTTP_ACCEPT_CHARSET'),
                accept_language=wsgi_env.get('HTTP_ACCEPT_LANGUAGE'))

            return endpoint(self, request, **kwargs)

        response = self._map_adapter.dispatch(call_view)

        return response(wsgi_env, start_response)

    def __call__(self, wsgi_env, start_response):
        return self._dispatch(wsgi_env, start_response)

    def url_for(self, *args, **kwargs):
        """ construct the url corresponding to an endpoint name and parameters

        Unfortunately will only work if the application has been bound to a
        wsgi request.  If it is not then there is not generally enough
        information to construct full urls.  TODO.
        """
        self._map_adapter(*args, **kwargs)
