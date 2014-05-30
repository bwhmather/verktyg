# -*- coding: utf-8 -*-
"""
    verktyg.views
    ~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import json

from werkzeug import Response
from verktyg.dispatch import BindingFactory, Binding


class View(BindingFactory):
    """ Wraps a function or callable so that it can be bound to a name in a
    dispatcher.
    """
    def __init__(self, name, action, methods=None, content_type=None, qs=None):
        self._name = name

        if methods is None:
            self._methods = set(['GET'])
        elif isinstance(methods, str):
            self._methods = set([methods])
        else:
            self._methods = methods

        self._content_type = content_type
        self._qs = qs
        self._action = action

    def __call__(self, env, req, *args, **kwargs):
        return self._action(env, req, *args, **kwargs)

    def get_bindings(self):
        for method in self._methods:
            yield Binding(self._name, self,
                          method=method,
                          content_type=self._content_type)


class ClassView(BindingFactory):
    def get_bindings(self):
        for method in set(['GET', 'HEAD', 'POST', 'PUT', 'DELETE']):  # TODO
            if hasattr(self, method):
                yield Binding(self.name, getattr(self, method),
                              method=method)


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
    def __init__(self, name, action,
                 methods=None, template=None,
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
        return Response(env.get_renderer(self._template)(res))


class JsonView(View):
    def __init__(self, name, action, methods=None, qs=None):
        super(JsonView, self).__init__(
            name, action, methods=methods,
            content_type='text/json', qs=qs
        )

    def __call__(self, env, req, *args, **kwargs):
        res = super(JsonView, self).__call__(env, req, *args, **kwargs)

        if isinstance(res, Response):
            # rendering already done
            return res

        if res is None:
            # no content
            return Response(status=204)

        return Response(json.dumps(res), content_type='text/json')


def expose(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add_bindings(TemplateView(name, f, *args, **kwargs))
        return f
    return decorator


def expose_html(*args, **kwargs):
    if 'content_type' not in kwargs:
        kwargs['content_type'] = 'text/html'
    return expose(*args, **kwargs)


def expose_json(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add_bindings(JsonView(name, f, *args, **kwargs))
        return f
    return decorator
