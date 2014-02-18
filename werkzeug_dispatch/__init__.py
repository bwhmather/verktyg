# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import json

from werkzeug import Response, Accept, parse_accept_header
from werkzeug.exceptions import NotFound, MethodNotAllowed, NotAcceptable


class BindingFactory(object):
    def get_bindings(self):
        raise NotImplementedError()


class Binding(BindingFactory):
    """Represents an action associated with a single combination of endpoint
    name and method.  In most cases you probably want to be using subclasses of
    `View` which can listen for multiple methods.

    `name`
        A hashable identifier.

    `method`
        An http method as an upper case string.

    `action`
        The action to perform if the binding is matched

    `content_type`
        A type/subtype formatted string representing the content type that the
        handler returns
    """
    def __init__(self, name, action, method='GET', content_type=None):
        self.name = name
        self.method = method
        self.action = action
        self.content_type = content_type

    def get_bindings(self):
        yield self


class View(BindingFactory):
    """ Wraps a function or callable so that it can be bound to a name in a
    dispatcher.
    """
    def __init__(self, name, action, *, methods={'GET'}, content_type=None):
        self._name = name
        self._methods = methods
        self._content_type = content_type
        self._action = action

    def __call__(self, env, req, *args, **kwargs):
        return self._action(env, req, *args, **kwargs)

    def get_bindings(self):
        for method in self._methods:
            yield Binding(self._name, self,
                          method=method,
                          content_type=self._content_type)


class TemplateView(View):
    """ Like `View` but if the value returned from the action is not an
    instance of `Response` it is rendered using the named template.

    :param name:
    :param action: called with environment, request and params to generate
                   response.  See `View`.
    :param template: either a string naming the template to be retrieved from
                     the environment or a callable applied to the result to
                     create an http `Response` object
    """
    def __init__(self, name, action, *,
                 methods={'GET'}, template=None,
                 content_type=None):
        super(TemplateView, self).__init__(
            name, action,
            methods=methods,
            content_type=content_type)
        self._template = template

    def __call__(self, env, req, *args, **kwargs):
        res = self._action(env, req, *args, **kwargs)
        if isinstance(res, Response):
            return res
        return env.get_renderer(self._template)(res)


def expose(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add(TemplateView(name, f, *args, **kwargs))
        return f
    return decorator


def expose_html(*args, **kwargs):
    if 'content_type' not in kwargs:
        kwargs['content_type'] = 'text/html'
    return expose(*args, **kwargs)


class JsonView(View):
    def __init__(self, name, action, *, methods={'GET'}):
        super(JsonView, self).__init__(name, action, methods=methods,
                                       content_type='text/json')

    def __call__(self, env, req, *args, **kwargs):
        res = super(JsonView, self).__call__(env, req, *args, **kwargs)
        if isinstance(res, Response):
            return res
        return Response(json.dumps(res), content_type='text/json')


def expose_json(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add(JsonView(name, f, *args, **kwargs))
        return f
    return decorator


class ClassView(BindingFactory):
    def get_bindings(self):
        for method in {'GET', 'HEAD', 'POST', 'PUT', 'DELETE'}:  # TODO
            if hasattr(self, method):
                yield Binding(self.name, getattr(self, method),
                              method=method)


class Dispatcher(BindingFactory):
    def __init__(self, views=[], *, default_view=TemplateView):
        """
        :param default_view: callable used to construct new views from
                             functions decorated with the `expose` method
        """
        self._default_view = default_view
        self._index = {}
        self._views = []

        for view in views:
            self.add(view)

    def expose(self, name, *args, **kwargs):
        """ Decorator to expose a function as a view.
        Does not modify the wrapped function.
        """
        def decorator(f):
            self.add(self._default_view(name, f, *args, **kwargs))
            return f
        return decorator

    def add(self, view_factory):
        """ Add views from view factory to this dispatcher.
        Dispatchers can be nested
        """
        for view in view_factory.get_bindings():
            if view.name not in self._index:
                self._index[view.name] = {}
            with_name = self._index[view.name]

            if view.method not in with_name:
                with_name[view.method] = {}
            with_method = with_name[view.method]

            with_method[view.content_type] = view.action

            self._views.append(view)

    def get_bindings(self):
        return iter(self._views)

    def lookup(self, name, method='GET', accept=Accept([('*', 1.0)])):
        with_name = self._index.get(name)
        if name not in self._index:
            # TODO this should possibly be 501 Not Implemented
            raise NotFound()

        with_method = with_name.get(method)
        if with_method is None:
            if method == 'HEAD' and 'GET' in with_name:
                with_method = with_name['GET']
            else:
                raise MethodNotAllowed()

        if isinstance(accept, str):
            accept = parse_accept_header(accept)
        content_type = accept.best_match(with_method.keys())

        action = with_method.get(content_type)
        if action is None:
            raise NotAcceptable()
        return action

