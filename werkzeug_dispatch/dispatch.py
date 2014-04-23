"""
    werkzeug_dispatch.dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.exceptions import NotImplemented, MethodNotAllowed

from werkzeug_dispatch.accept import Representation, select_representation


class BindingFactory(object):
    def get_bindings(self):
        raise NotImplementedError()


class Binding(BindingFactory, Representation):
    """Represents an action associated with a single combination of endpoint
    name, method and content-type.  In most cases you probably want to be using
    subclasses of `View` which can listen for multiple methods.

    `name`
        A hashable identifier.

    `method`
        An http method as an upper case string.

    `action`
        The action to perform if the binding is matched

    `content_type`
        A type/subtype formatted string representing the content type that the
        handler returns
        See `Representation`

    `language`
        See `Representation`

    `charser`
        See `Representation`

    `qs`
        Quality of source.  Multiplied by the accept q value to give quality of
        biding if mimetypes match.  Name by convention from other servers
    """
    def __init__(self, name, action, method='GET', *,
                 content_type=None, language=None, charset=None, qs=None):
        self.name = name
        self.method = method
        self.action = action

        Representation.__init__(
            self, qs=qs,
            content_type=content_type,
            language=language,
            charset=charset
        )

    def get_bindings(self):
        yield self

    def __repr__(self):
        return '<%s %s %s %s>' % (
            self.__class__.__name__,
            repr(self.name),
            repr(self.method),
            repr(self.content_type),
        )


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

        representation = select_representation(
            with_method,
            accept=accept,
            accept_language=accept_language,
            accept_charset=accept_charset
        )

        return representation.action
