# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import json

from werkzeug import Response, Accept


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
    def __init__(self, name, method, action, content_type=None):
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
            yield Binding(self._name, method, self, self._content_type)


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
    def __init__(self, name, action, *, methods={'GET'}, template=None):
        super(TemplateView, self).__init__(name, action, methods=methods)
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


class JsonView(View):
    def __init__(self, name, action, *, methods={'GET'}):
        super(JsonView, self).__init__(name, action, methods=methods,
                                       content_type='text/json')

    def __call__(self, env, req, *args, **kwargs):
        res = super(JsonView, self).__call__(env, req, *args, **kwargs)
        if isinstance(res, Response):
            return res
        return Response(json.dumps(res), content_type='text/json')


def expose_json(dispatcher, name, f, *args, **kwargs):
    def decorator(f):
        dispatcher.add(JsonView(name, f, *args, **kwargs))
        return f
    return decorator


class ClassView(BindingFactory):
    def get_bindings(self):
        for method in {'GET', 'HEAD', 'POST', 'PUT', 'DELETE'}:  # TODO
            if hasattr(self, method):
                yield Binding(self.name, method, getattr(self, method))


class Dispatcher(BindingFactory):
    def __init__(self, views=[], *, default_view=TemplateView):
        """
        :param default_view: callable used to construct new views from
                             functions decorated with the `expose` method
        """
        self._default_view = default_view
        self._views = {}

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
        # TODO save results of lookups
        for view in view_factory.get_bindings():
            if not view.name in self._views:
                self._views[view.name] = {}
            if not view.method in self._views[view.name]:
                self._views[view.name][view.method] = {}
            if not view.content_type in self._views[view.name]:
                self._views[view.name][view.method][view.content_type] = {}

            self._views[view.name][view.method][view.content_type] = view.action

    def get_bindings(self):
        return iter(self._views.items())

    def lookup(self, method, name, accept=Accept([('*', 1.0)])):
        if name not in self._views:
            return None

        if method not in self._views[name]:
            if method != 'HEAD':
                return None
            elif 'GET' in self._views[name]:
                method = 'GET'

        content_type = accept.best_match(self._views[name][method].keys())
        if content_type in self._views[name][method]:
            return self._views[name][method][content_type]
        else:
            return None

