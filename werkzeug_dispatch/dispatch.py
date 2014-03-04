# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.exceptions import NotImplemented, MethodNotAllowed, NotAcceptable

from werkzeug_dispatch.bindings import BindingFactory


class Dispatcher(BindingFactory):
    def __init__(self, views=[]):
        self._index = {}
        self._views = []

        for view in views:
            self.add(view)

    def add(self, view_factory):
        """ Add views from view factory to this dispatcher.
        Dispatchers can be nested
        """
        for view in view_factory.get_bindings():
            if view.name not in self._index:
                self._index[view.name] = {}
            with_name = self._index[view.name]

            if view.method not in with_name:
                with_name[view.method] = []
            with_method = with_name[view.method]

            with_method.append(view)

            self._views.append(view)

    def get_bindings(self):
        return iter(self._views)

    def lookup(self, name, method='GET',
               accept='*/*', accept_language=None, accept_charset=None):
        with_name = self._index.get(name)
        if name not in self._index:
            raise NotImplemented()

        with_method = with_name.get(method)
        if with_method is None:
            if method == 'HEAD' and 'GET' in with_name:
                with_method = with_name['GET']
            else:
                raise MethodNotAllowed()

        max_quality = tuple()
        best = None
        for binding in with_method:
            try:
                quality = binding.quality(accept=accept,
                                          accept_language=accept_language,
                                          accept_charset=accept_charset)
            except NotAcceptable:
                continue

            if not isinstance(quality, tuple):
                quality = (quality,)

            # Later bindings take precedence
            if quality >= max_quality:
                best = binding
                max_quality = quality

        if best is None:
            raise NotAcceptable()

        return best.action
