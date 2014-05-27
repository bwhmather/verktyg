# -*- coding: utf-8 -*-
"""
    verktyg.exception_dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.exceptions import NotAcceptable

from verktyg.accept import Representation, select_representation


class ExceptionBindingFactory(object):
    def get_bindings(self):
        raise NotImplementedError()


class ExceptionBinding(ExceptionBindingFactory, Representation):
    """An action associated with an exception class and providing a particular
    representation.

    `exception_class`
        Binding can be used to render instances of this class and all
        subclasses

    `action`
        The action to perform if the binding is matched.
        Function accepting `(application, request, exception)` and returning
        a werkzeug response object.
    """
    def __init__(self, exception_class, action, **kwargs):

        self.exception_class = exception_class
        self.action = action

        super(ExceptionBinding, self).__init__(**kwargs)

    def get_bindings(self):
        yield self

    def __repr__(self):
        return '<%s %s %s>' % (
            self.__class__.__name__,
            repr(self.exception_class),
            repr(self.content_type),
        )


class ExceptionDispatcher(ExceptionBindingFactory):
    def __init__(self, bindings=[]):
        self._bindings = {}

        for binding in bindings:
            self.add(binding)

    def add(self, handler_factory):
        """Bind a handlers from a handler factory to render exceptions of a
        particular class or representation.
        Dispatchers can be nested

        :param exception_factory:
            an instance of `ExceptionBindingFactory` or other object provifing
            a `get_bindings` method which returns an iterator that of exception
            bindings.  Both `ExceptionBinding` and `ExceptionDispatcher`
            implement this interface so both can be nested using a call to
            `add`
        """
        for binding in handler_factory.get_bindings():
            if binding.exception_class not in self._bindings:
                self._bindings[binding.exception_class] = []
            self._bindings[binding.exception_class].append(binding)

    def get_bindings(self):
        return iter(self._bindings)

    def lookup(self, exception_class,
               accept='*/*', accept_language=None, accept_charset=None):
        """ Given an exception class and the contents of a requests accept
        headers, returns the corresponding exception handler.

        :param exception_class:
            Matched to exception handlers using `isinstance`.

        :param accept:
            See `verktyg.accept.select_representation` for details

        :param accept_language:
            See `verktyg.accept.select_representation` for details

        :param accept_charset:
            See `verktyg.accept.select_representation` for details

        :return:
            A callable object accepting am application object, a request, and
            an exception and returning a werkzeug response
        """
        # Use the method resolution order of the exception to rank handlers
        for cls in exception_class.mro():
            if cls not in self._bindings:
                continue

            try:
                binding = select_representation(
                    self._bindings[cls],
                    accept=accept,
                    accept_language=accept_language,
                    accept_charset=accept_charset
                )

                return binding.action

            except NotAcceptable:
                continue

        return None
