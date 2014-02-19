# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch.bindings
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""


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
