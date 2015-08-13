"""
    verktyg.views
    ~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import json

from verktyg.responses import Response
from verktyg.dispatch import BindingFactory, Binding


class View(BindingFactory):
    """ Wraps a function or callable so that it can be bound to a name in a
    dispatcher.
    """
    def __init__(self, name, action, *,
                 methods=None, content_type=None, qs=None):
        self._name = name

        if methods is None:
            self._methods = {'GET'}
        elif isinstance(methods, str):
            self._methods = {methods}
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
        for method in {'GET', 'HEAD', 'POST', 'PUT', 'DELETE'}:  # TODO
            if hasattr(self, method):
                yield Binding(self.name, getattr(self, method),
                              method=method)


class JsonView(View):
    def __init__(self, name, action, methods=None, qs=None):
        super(JsonView, self).__init__(
            name, action, methods=methods,
            content_type='application/json', qs=qs
        )

    def __call__(self, env, req, *args, **kwargs):
        res = super(JsonView, self).__call__(env, req, *args, **kwargs)

        if isinstance(res, Response):
            # rendering already done
            return res

        if res is None:
            # no content
            return Response(status=204)

        if env.debug:
            json_response = json.dumps(res, indent=4)
        else:
            json_response = json.dumps(res, separators=(',', ':'))

        return Response(json_response, content_type='application/json')


def expose(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add_bindings(View(name, f, *args, **kwargs))
        return f
    return decorator


def expose_json(dispatcher, name, *args, **kwargs):
    def decorator(f):
        dispatcher.add_bindings(JsonView(name, f, *args, **kwargs))
        return f
    return decorator
