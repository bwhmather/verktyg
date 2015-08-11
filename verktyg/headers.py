"""
    verktyg.headers
    ~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.

"""
from werkzeug._internal import _missing
from werkzeug.http import dump_options_header, quote_header_value

from verktyg.datastructures import is_immutable
from verktyg import exceptions


def _options_header_vkw(value, kw):
    return dump_options_header(value, dict((k.replace('_', '-'), v)
                                           for k, v in kw.items()))


def _unicodify_header_value(value):
    if isinstance(value, bytes):
        value = value.decode('latin-1')
    if not isinstance(value, str):
        value = str(value)
    return value


class Headers(object):
    """An object that stores some headers.  It has a dict-like interface
    but is ordered and can store the same keys multiple times.

    This data structure is useful if you want a nicer way to handle WSGI
    headers which are stored as tuples in a list.

    From Werkzeug 0.3 onwards, the :exc:`KeyError` raised by this class is
    also a subclass of the :class:`~exceptions.BadRequest` HTTP exception
    and will render a page for a ``400 BAD REQUEST`` if caught in a
    catch-all for HTTP exceptions.

    Headers is mostly compatible with the Python
    :class:`wsgiref.headers.Headers` class, with the exception of
    `__getitem__`.  :mod:`wsgiref` will return `None` for
    ``headers['missing']``, whereas :class:`Headers` will raise a
    :class:`KeyError`.

    To create a new :class:`Headers` object pass it a list or dict of headers
    which are used as default values.  This does not reuse the list passed
    to the constructor for internal usage.

    :param defaults:
        The list of default values for the :class:`Headers`.
    """

    def __init__(self, defaults=None):
        self._list = []
        if defaults is not None:
            if isinstance(defaults, (list, Headers)):
                self._list.extend(defaults)
            else:
                self.extend(defaults)

    def __getitem__(self, key, _get_mode=False):
        if not _get_mode:
            if isinstance(key, int):
                return self._list[key]
            elif isinstance(key, slice):
                return self.__class__(self._list[key])
        if not isinstance(key, str):
            raise exceptions.BadRequestKeyError(key)
        ikey = key.lower()
        for k, v in self._list:
            if k.lower() == ikey:
                return v
        # micro optimization: if we are in get mode we will catch that
        # exception one stack level down so we can raise a standard
        # key error instead of our special one.
        if _get_mode:
            raise KeyError()
        raise exceptions.BadRequestKeyError(key)

    def __eq__(self, other):
        return other.__class__ is self.__class__ and \
            set(other._list) == set(self._list)

    def __ne__(self, other):
        return not self.__eq__(other)

    def get(self, key, default=None, type=None, as_bytes=False):
        """Return the default value if the requested data doesn't exist.
        If `type` is provided and is a callable it should convert the value,
        return it or raise a :exc:`ValueError` if that is not possible.  In
        this case the function will return the default as if the value was not
        found:

        >>> d = Headers([('Content-Length', '42')])
        >>> d.get('Content-Length', type=int)
        42

        If a headers object is bound you must not add unicode strings
        because no encoding takes place.

        :param key:
            The key to be looked up.
        :param default:
            The default value to be returned if the key can't be looked up.  If
            not further specified `None` is returned.
        :param type:
            A callable that is used to cast the value in the :class:`Headers`.
            If a :exc:`ValueError` is raised by this callable the default value
            is returned.
        :param as_bytes:
            Return bytes instead of unicode strings.
        """
        try:
            rv = self.__getitem__(key, _get_mode=True)
        except KeyError:
            return default
        if as_bytes:
            rv = rv.encode('latin1')
        if type is None:
            return rv
        try:
            return type(rv)
        except ValueError:
            return default

    def getlist(self, key, type=None, as_bytes=False):
        """Return the list of items for a given key. If that key is not in the
        :class:`Headers`, the return value will be an empty list.  Just as
        :meth:`get` :meth:`getlist` accepts a `type` parameter.  All items will
        be converted with the callable defined there.

        :param key:
            The key to be looked up.
        :param type:
            A callable that is used to cast the value in the :class:`Headers`.
            If a :exc:`ValueError` is raised by this callable the value will be
            removed from the list.
        :param as_bytes:
            Return bytes instead of unicode strings.
        :return:
            A :class:`list` of all the values for the key.
        """
        ikey = key.lower()
        result = []
        for k, v in self:
            if k.lower() == ikey:
                if as_bytes:
                    v = v.encode('latin1')
                if type is not None:
                    try:
                        v = type(v)
                    except ValueError:
                        continue
                result.append(v)
        return result

    def get_all(self, name):
        """Return a list of all the values for the named field.

        This method is compatible with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.get_all` method.
        """
        return self.getlist(name)

    def items(self, lower=False):
        for key, value in self:
            if lower:
                key = key.lower()
            yield key, value

    def keys(self, lower=False):
        for key, _ in self.items(lower):
            yield key

    def values(self):
        for _, value in self.items():
            yield value

    def extend(self, iterable):
        """Extend the headers with a dict or an iterable yielding keys and
        values.
        """
        if isinstance(iterable, dict):
            for key, value in iterable.items():
                if isinstance(value, (tuple, list)):
                    for v in value:
                        self.add(key, v)
                else:
                    self.add(key, value)
        else:
            for key, value in iterable:
                self.add(key, value)

    def __delitem__(self, key, _index_operation=True):
        if _index_operation and isinstance(key, (int, slice)):
            del self._list[key]
            return
        key = key.lower()
        new = []
        for k, v in self._list:
            if k.lower() != key:
                new.append((k, v))
        self._list[:] = new

    def remove(self, key):
        """Remove a key.

        :param key:
            The key to be removed.
        """
        return self.__delitem__(key, _index_operation=False)

    def pop(self, key=None, default=_missing):
        """Removes and returns a key or index.

        :param key:
            The key to be popped.  If this is an integer the item at that
            position is removed, if it's a string the value for that key is.
            If the key is omitted or `None` the last item is removed.
        :return:
            An item.
        """
        if key is None:
            return self._list.pop()
        if isinstance(key, int):
            return self._list.pop(key)
        try:
            rv = self[key]
            self.remove(key)
        except KeyError:
            if default is not _missing:
                return default
            raise
        return rv

    def popitem(self):
        """Removes a key or index and returns a (key, value) item."""
        return self.pop()

    def __contains__(self, key):
        """Check if a key is present."""
        try:
            self.__getitem__(key, _get_mode=True)
        except KeyError:
            return False
        return True

    has_key = __contains__

    def __iter__(self):
        """Yield ``(key, value)`` tuples."""
        return iter(self._list)

    def __len__(self):
        return len(self._list)

    def add(self, _key, _value, **kw):
        """Add a new header tuple to the list.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes::

        >>> d = Headers()
        >>> d.add('Content-Type', 'text/plain')
        >>> d.add('Content-Disposition', 'attachment', filename='foo.png')

        The keyword argument dumping uses :func:`dump_options_header`
        behind the scenes.
        """
        if kw:
            _value = _options_header_vkw(_value, kw)
        _value = _unicodify_header_value(_value)
        self._validate_value(_value)
        self._list.append((_key, _value))

    def _validate_value(self, value):
        if not isinstance(value, str):
            raise TypeError('Value should be unicode.')
        if u'\n' in value or u'\r' in value:
            raise ValueError('Detected newline in header value.  This is '
                             'a potential security problem')

    def add_header(self, _key, _value, **_kw):
        """Add a new header tuple to the list.

        An alias for :meth:`add` for compatibility with the :mod:`wsgiref`
        :meth:`~wsgiref.headers.Headers.add_header` method.
        """
        self.add(_key, _value, **_kw)

    def clear(self):
        """Clears all headers."""
        del self._list[:]

    def set(self, _key, _value, **kw):
        """Remove all header tuples for `key` and add a new one.  The newly
        added key either appears at the end of the list if there was no
        entry or replaces the first one.

        Keyword arguments can specify additional parameters for the header
        value, with underscores converted to dashes.  See :meth:`add` for
        more information.

        :param key:
            The key to be inserted.
        :param value:
            The value to be inserted.
        """
        if kw:
            _value = _options_header_vkw(_value, kw)
        _value = _unicodify_header_value(_value)
        self._validate_value(_value)
        if not self._list:
            self._list.append((_key, _value))
            return
        listiter = iter(self._list)
        ikey = _key.lower()
        for idx, (old_key, old_value) in enumerate(listiter):
            if old_key.lower() == ikey:
                # replace first ocurrence
                self._list[idx] = (_key, _value)
                break
        else:
            self._list.append((_key, _value))
            return
        self._list[idx + 1:] = [t for t in listiter if t[0].lower() != ikey]

    def setdefault(self, key, value):
        """Returns the value for the key if it is in the dict, otherwise it
        returns `default` and sets that value for `key`.

        :param key:
            The key to be looked up.
        :param default:
            The default value to be returned if the key is not in the dict.  If
            not further specified it's `None`.
        """
        if key in self:
            return self[key]
        self.set(key, value)
        return value

    def __setitem__(self, key, value):
        """Like :meth:`set` but also supports index/slice based setting."""
        if isinstance(key, (slice, int)):
            if isinstance(key, int):
                value = [value]
            value = [(k, _unicodify_header_value(v)) for (k, v) in value]
            [self._validate_value(v) for (k, v) in value]
            if isinstance(key, int):
                self._list[key] = value[0]
            else:
                self._list[key] = value
        else:
            self.set(key, value)

    def to_list(self, charset='iso-8859-1'):
        """Convert the headers into a list suitable for WSGI."""
        from warnings import warn
        warn(DeprecationWarning('Method removed, use to_wsgi_list instead'),
             stacklevel=2)
        return self.to_wsgi_list()

    def to_wsgi_list(self):
        """Convert the headers into a list suitable for WSGI.

        The values are byte strings in Python 2 converted to latin1 and unicode
        strings in Python 3 for the WSGI server to encode.

        :return: list
        """
        return list(self)

    def copy(self):
        return self.__class__(self._list)

    def __copy__(self):
        return self.copy()

    def __str__(self):
        """Returns formatted headers suitable for HTTP transmission."""
        strs = []
        for key, value in self.to_wsgi_list():
            strs.append('%s: %s' % (key, value))
        strs.append('\r\n')
        return '\r\n'.join(strs)

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            list(self)
        )


class ImmutableHeadersMixin(object):
    """Makes a :class:`Headers` immutable.  We do not mark them as
    hashable though since the only usecase for this datastructure
    in Werkzeug is a view on a mutable structure.

    :private:
    """

    def __delitem__(self, key):
        is_immutable(self)

    def __setitem__(self, key, value):
        is_immutable(self)
    set = __setitem__

    def add(self, item):
        is_immutable(self)
    remove = add_header = add

    def extend(self, iterable):
        is_immutable(self)

    def insert(self, pos, value):
        is_immutable(self)

    def pop(self, index=-1):
        is_immutable(self)

    def popitem(self):
        is_immutable(self)

    def setdefault(self, key, default):
        is_immutable(self)


class EnvironHeaders(ImmutableHeadersMixin, Headers):
    """Read only version of the headers from a WSGI environment.  This
    provides the same interface as `Headers` and is constructed from
    a WSGI environment.

    From Werkzeug 0.3 onwards, the `KeyError` raised by this class is also a
    subclass of the :exc:`~exceptions.BadRequest` HTTP exception and will
    render a page for a ``400 BAD REQUEST`` if caught in a catch-all for
    HTTP exceptions.
    """

    def __init__(self, environ):
        self.environ = environ

    def __eq__(self, other):
        return self.environ is other.environ

    def __getitem__(self, key, _get_mode=False):
        # _get_mode is a no-op for this class as there is no index but
        # used because get() calls it.
        key = key.upper().replace('-', '_')
        if key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            return _unicodify_header_value(self.environ[key])
        return _unicodify_header_value(self.environ['HTTP_' + key])

    def __len__(self):
        # the iter is necessary because otherwise list calls our
        # len which would call list again and so forth.
        return len(list(iter(self)))

    def __iter__(self):
        for key, value in self.environ.items():
            if key.startswith('HTTP_') and key not in \
               ('HTTP_CONTENT_TYPE', 'HTTP_CONTENT_LENGTH'):
                yield (key[5:].replace('_', '-').title(),
                       _unicodify_header_value(value))
            elif key in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
                yield (key.replace('_', '-').title(),
                       _unicodify_header_value(value))

    def copy(self):
        raise TypeError('cannot create %r copies' % self.__class__.__name__)
