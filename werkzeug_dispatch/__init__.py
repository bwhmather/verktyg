# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import Response

import json


class ViewFactory(object):
    def get_views(self):
        raise NotImplementedError()


class View(ViewFactory):
    """ Wraps a function or callable so that it can be bound to a name in a
    dispatcher.
    """
    def __init__(self, name, action, *, methods={'GET'}, accept='*'):
        self._name = name
        self._action = action
        self._methods = methods

    def __call__(self, environment, request, *args, **kwargs):
        return self._action(environment, request, *args, **kwargs)

    def get_views(self):
        for method in self._methods:
            yield ((method, self._name), self)


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
        return env.get_template(self._template).render(res)


class JsonView(View):
    def __init__(self, name, action, *, methods={'GET'}):
        super(JsonView, self).__init__(name, action, methods=methods,
                                       accept='text/json')

    def __call__(self, env, req, *args, **kwargs):
        res = super(JsonView, self).__call__(env, req, *args, **kwargs)
        if isinstance(res, Response):
            return res
        return Response(json.dumps(res))


def ClassView(ViewFactory):
    def get_views(self):
        for method in {'GET', 'HEAD', 'POST', 'PUT', 'DELETE'}:  # TODO
            if hasattr(self, method):
                yield ((method, self._name), getattr(self, method))


class Dispatcher(ViewFactory):
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
        for (method, name), action in view_factory.get_views():
            if not name in self._views:
                self._views[name] = {}
            if not method in self._views[name]:
                self._views[name][method] = {}

            self._views[name][method] = action

    def get_views(self):
        return iter(self._views.items())

    def lookup(self, method, name):
        if not name in self._views:
            return None

        if method in self._views[name]:
            return self._views[name][method]
        elif method == 'HEAD' and 'GET' in self._views[name]:
            return self._views[name]['GET']
