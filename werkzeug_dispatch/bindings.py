# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.bindings
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug_dispatch.accept import Representation


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

    `qs`
        Quality of source.  Multiplied by the accept q value to give quality of
        biding if mimetypes match.  Name by convention from other servers
    """
    def __init__(self, name, action, method='GET',
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
            repr(self._content_type)
        )
