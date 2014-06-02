# -*- coding: utf-8 -*-
"""
    verktyg.exception_dispatch
    ~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.exceptions import NotAcceptable

from verktyg.accept import Representation, select_representation


class ExceptionHandlerFactory(object):
    def get_exception_handlers(self):
        raise NotImplementedError()


class ExceptionHandler(ExceptionHandlerFactory, Representation):
    """An action associated with an exception class and providing a particular
    representation.

    `exception_class`
        Binding can be used to render instances of this class and all
        subclasses

    `action`
        The action to perform if the handler is matched.
        Function accepting `(application, request, exception)` and returning
        a werkzeug response object.
    """
    def __init__(self, exception_class, action, **kwargs):

        self.exception_class = exception_class
        self.action = action

        super(ExceptionHandler, self).__init__(**kwargs)

    def get_exception_handlers(self):
        yield self

    def __repr__(self):
        return '<%s %s %s>' % (
            self.__class__.__name__,
            repr(self.exception_class),
            repr(self.content_type),
        )


class ExceptionDispatcher(ExceptionHandlerFactory):
    def __init__(self, handlers=[]):
        self._handlers = {}

        self.add_exception_handlers(*handlers)

    def add_exception_handlers(self, *factories):
        """Bind a handlers from a handler factory to render exceptions of a
        particular class or representation.
        Dispatchers can be nested

        :param factories:
            a number of instances of `ExceptionHandlerFactory` or other objects
            providing a `get_exception_handlers` method which returns an
            iterator that yields exception handlers.  Both `ExceptionHandler`
            and `ExceptionDispatcher` implement this interface so both can be
            nested using a call to `add_exception_handlers`
        """
        for factory in factories:
            for handler in factory.get_exception_handlers():
                if handler.exception_class not in self._handlers:
                    self._handlers[handler.exception_class] = []
                self._handlers[handler.exception_class].append(handler)

    def get_exception_handlers(self):
        return iter(self._handlers)

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
            if cls not in self._handlers:
                continue

            try:
                handler = select_representation(
                    self._handlers[cls],
                    accept=accept,
                    accept_language=accept_language,
                    accept_charset=accept_charset
                )

                return handler.action

            except NotAcceptable:
                continue

        return None
