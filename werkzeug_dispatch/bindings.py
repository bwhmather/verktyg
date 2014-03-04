# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.bindings
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import parse_accept_header
from werkzeug.exceptions import NotAcceptable

_DEFAULT = object()


class BindingFactory(object):
    def get_bindings(self):
        raise NotImplementedError()


class Binding(BindingFactory):
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
                 content_type=None, qs=_DEFAULT):
        self.name = name
        self.method = method
        self.action = action

        self._content_type = content_type
        if qs is _DEFAULT:
            if content_type is None:
                self._qs = 0.001
            else:
                self._qs = 1.0

    def get_bindings(self):
        yield self

    def quality(self, accept=None, accept_encoding=None, accept_language=None):
        """ Returns a number or tuple of numbers representing the quality of
        the match if one is found.  Otherwise returns None
        """
        accept = parse_accept_header(accept)

        if self._content_type is None:
            return self._qs

        quality = self._qs * accept.quality(self._content_type)
        if not quality:
            raise NotAcceptable()

        return quality

    def __repr__(self):
        return '<%s %s %s %s>' % (
            self.__class__.__name__,
            repr(self.name),
            repr(self.method),
            repr(self._content_type)
        )
