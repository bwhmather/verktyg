"""
    werkzeug_dispatch.error_handling
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    Exception rendering utilities.

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug.exceptions import NotAcceptable

from werkzeug_dispatch.bindings import BindingFactory
from werkzeug_dispatch.accept import select_representation


class ExceptionDispatcher(BindingFactory):
    def __init__(self, bindings=[]):
        self._bindings = {}

        for binding in bindings:
            self.add(bindings)

    def add(self, handler_factory):
        """Bind a handlers from a handler factory to render exceptions of a
        particular class or representation.
        Dispatchers can be nested
        """
        for binding in handler_factory.get_bindings():
            if binding.exception_class not in self._bindings:
                self._bindings[binding.exception_class] = []
            self._bindings[binding.exception_class].append(binding)

    def get_bindings(self):
        return iter(self._bindings)

    def lookup(self, exception_class,
               accept='*/*', accept_language=None, accept_charset=None):
        # Use the method resolution order of the exception to rank handlers
        for cls in exception_class.__mro__:
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
