"""
    verktyg.application
    ~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import sys

from werkzeug.local import Local, LocalManager
from werkzeug.utils import redirect

from verktyg.exception_dispatch import (
    ExceptionDispatcher, ExceptionHandler
)
from verktyg.routing import URLMap, Route, RequestRedirect
from verktyg.dispatch import Dispatcher
from verktyg.views import expose
from verktyg.requests import BaseRequest
from verktyg import requests


def _default_redirect_handler(app, req, exc_type, exc_value, exc_traceback):
    return redirect(exc_value.new_url, exc_value.code)


class BaseApplication(object):
    def __init__(
                self, *, routes, converters, bindings, handlers,
                middleware, request_class
            ):
        self._url_map = URLMap(routes, converters=converters)
        self._dispatcher = Dispatcher(bindings)
        self._exception_dispatcher = ExceptionDispatcher(handlers)

        self.request_class = request_class

        # reference to the bottom of a stack of wsgi middleware wrapping
        # :method:`_dispatch_request`. Invoked by :method:`__call__`.
        # Essentially the real wsgi application.
        self._stack = self._wsgi_inner
        for wrapper, args, kwargs in middleware:
            self._stack = wrapper(self._stack, *args, **kwargs)

        # TODO provide a way of adding request specific variables.  Need to be
        # able to register name, `(Application, wsgi_env) -> value` pairs
        # Alternatively get rid of this entirely as it's a massive hack
        self._local = Local()
        self._wsgi_env = self._local('wsgi_env')
        self._map_adapter = self._local('map_adapter')

        local_manager = LocalManager([self._local])
        # TODO
        self._stack = local_manager.make_middleware(self._stack)

    def _bind(self, wsgi_env):
        self._local.wsgi_env = wsgi_env
        self._local.map_adapter = self._url_map.bind_to_environ(wsgi_env)

    def _get_response(self, request):
        try:
            endpoint, kwargs = self._map_adapter.match()

            binding = self._dispatcher.lookup(
                endpoint,
                method=request.environ.get('REQUEST_METHOD'),
                accept=request.environ.get('HTTP_ACCEPT'),
                accept_charset=request.environ.get('HTTP_ACCEPT_CHARSET'),
                accept_language=request.environ.get('HTTP_ACCEPT_LANGUAGE')
            )

            request.binding = binding

            return binding(self, request, **kwargs)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()

            handler = self._exception_dispatcher.lookup(
                exc_type,
                accept=request.environ.get('HTTP_ACCEPT'),
                accept_charset=request.environ.get('HTTP_ACCEPT_CHARSET'),
                accept_language=request.environ.get('HTTP_ACCEPT_LANGUAGE')
            )
            if handler is None:
                raise

            return handler(self, request, exc_type, exc_value, exc_traceback)

    def _wsgi_inner(self, wsgi_env, start_response):
        self._bind(wsgi_env)
        with self.request_class(wsgi_env) as request:
            with self._get_response(request) as response:
                yield from response(wsgi_env, start_response)

    def __call__(self, wsgi_env, start_response):
        wsgi_env['verktyg.application'] = self
        return self._stack(wsgi_env, start_response)

    def url_for(self, endpoint, **kwargs):
        """ construct the url corresponding to an endpoint name and parameters

        Unfortunately will only work if the application has been bound to a
        wsgi request.  If it is not then there is not generally enough
        information to construct full urls.  TODO.
        """
        return self._map_adapter.build(endpoint, values=kwargs)


class ApplicationBuilder(object):
    def __init__(
                self, *,
                default_redirect_handler=True, default_request_mixins=True
            ):
        self._application_bases = [BaseApplication]
        self._request_bases = [BaseRequest]

        self._middleware = []

        self._routes = []
        self._converters = {}
        self._bindings = []
        self._handlers = []

        if default_redirect_handler:
            self.add_exception_handlers(
                ExceptionHandler(RequestRedirect, _default_redirect_handler),
            )

        if default_request_mixins:
            self.add_request_mixins(
                requests.BaseRequest, requests.AcceptMixin,
                requests.ETagRequestMixin, requests.UserAgentMixin,
                requests.AuthorizationMixin,
                requests.CommonRequestDescriptorsMixin,
            )

    def add_application_mixins(self, *mixins):
        for mixin in mixins:
            if mixin not in self._application_bases:
                self._application_bases.append(mixin)

    def add_request_mixins(self, *mixins):
        for mixin in mixins:
            if mixin not in self._request_bases:
                self._request_bases.append(mixin)

    def add_converters(self, **converters):
        self._converters.update(**converters)

    def add_routes(self, *routes):
        self._routes.extend(routes)

    def add_bindings(self, *views):
        self._bindings.extend(views)

    def expose(self, endpoint=None, *args, **kwargs):
        """ Decorator to bind a function to an endpoint and optionally the
        endpoint to a route.
        """
        def wrapper(f):
            nonlocal endpoint
            if endpoint is None:
                endpoint = f.__name__

            route = kwargs.pop('route', None)
            if route is not None:
                self.add_routes(Route(route, endpoint=endpoint))

            return expose(self, endpoint, *args, **kwargs)(f)
        return wrapper

    def add_middleware(self, middleware, *args, **kwargs):
        """ Wrap the application in a layer of wsgi middleware.

        :param middleware:
            a function which takes a wsgi application as it's first argument
            and returns a new wsgi application.  Any other args or kwargs are
            passed after.
        """
        self._middleware.append((middleware, args, kwargs))

    def add_exception_handlers(self, *handlers):
        self._handlers.extend(handlers)

    def add_exception_handler(self, exception_class, handler, **kwargs):
        """ Bind a function to render exceptions of the given class and all
        sub classes.

        Exception handlers take three arguments:
          * a reference to the application
          * a request object
          * the class of the exception
          * the exception instance
          * a traceback
        The last three arguments are the same as the return value of
        `sys.exc_info()`
        """
        self.add_exception_handlers(
            ExceptionHandler(exception_class, handler, **kwargs)
        )

    def exception_handler(self, exception_class, **kwargs):
        """ Decorator that can be used to bind an exception handler to the
        application.  Takes the same arguments as `ExceptionHandler`
        """
        def wrapper(handler):
            self.add_exception_handler(exception_class, handler, **kwargs)
            return handler
        return wrapper

    def __call__(self):
        class Application(*self._application_bases):
            pass

        class Request(*self._request_bases):
            pass

        return Application(
            routes=iter(self._routes),
            converters=dict(self._converters.items()),
            bindings=iter(self._bindings),
            handlers=iter(self._handlers),
            middleware=iter(self._middleware),
            request_class=Request,
        )
