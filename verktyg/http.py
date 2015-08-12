"""
    verktyg.http
    ~~~~~~~~~~~~

    This covers some of the more HTTP centric features of WSGI, some other
    utilities such as cookie handling are documented in the `werkzeug.utils`
    module.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import re
import sys
import codecs
from time import time, gmtime
from email.utils import parsedate_tz
from urllib.request import parse_http_list as _parse_list_header
from datetime import datetime, timedelta
from hashlib import md5
import base64

from werkzeug._internal import (
    _cookie_quote, _make_cookie_domain, _cookie_parse_impl,
    _missing, _empty_stream,
)
from werkzeug._compat import to_unicode, to_bytes, make_literal_wrapper
from werkzeug.urls import iri_to_uri
from werkzeug import datastructures
from werkzeug.datastructures import is_immutable

from verktyg import exceptions


_cookie_charset = 'latin1'
# for explanation of "media-range", etc. see Sections 5.3.{1,2} of RFC 7231
_accept_re = re.compile(
    r'''(                       # media-range capturing-parenthesis
              [^\s;,]+              # type/subtype
              (?:[ \t]*;[ \t]*      # ";"
                (?:                 # parameter non-capturing-parenthesis
                  [^\s;,q][^\s;,]*  # token that doesn't start with "q"
                |                   # or
                  q[^\s;,=][^\s;,]* # token that is more than just "q"
                )
              )*                    # zero or more parameters
            )                       # end of media-range
            (?:[ \t]*;[ \t]*q=      # weight is a "q" parameter
              (\d*(?:\.\d+)?)       # qvalue capturing-parentheses
              [^,]*                 # "extension" accept params: who cares?
            )?                      # accept params are optional
        ''', re.VERBOSE)
_locale_delim_re = re.compile(r'[_-]')
_token_chars = frozenset("!#$%&'*+-.0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
                         '^_`abcdefghijklmnopqrstuvwxyz|~')
_etag_re = re.compile(r'([Ww]/)?(?:"(.*?)"|(.*?))(?:\s*,\s*|$)')
_unsafe_header_chars = set('()<>@,;:\"/[]?={} \t')
_quoted_string_re = r'"[^"\\]*(?:\\.[^"\\]*)*"'
_option_header_piece_re = re.compile(
    r';\s*(%s|[^\s;=]+)\s*(?:=\s*(%s|[^;]+))?\s*' %
    (_quoted_string_re, _quoted_string_re)
)

_entity_headers = frozenset([
    'allow', 'content-encoding', 'content-language', 'content-length',
    'content-location', 'content-md5', 'content-range', 'content-type',
    'expires', 'last-modified'
])
_hop_by_hop_headers = frozenset([
    'connection', 'keep-alive', 'proxy-authenticate',
    'proxy-authorization', 'te', 'trailer', 'transfer-encoding',
    'upgrade'
])

# reexport status codes.  Original definition is in in exceptions to avoid
# circular dependency
HTTP_STATUS_CODES = exceptions.HTTP_STATUS_CODES


def wsgi_to_bytes(data):
    """coerce wsgi unicode represented bytes to real ones

    """
    if isinstance(data, bytes):
        return data
    return data.encode('latin1')  # XXX: utf8 fallback?


def bytes_to_wsgi(data):
    assert isinstance(data, bytes), 'data must be bytes'
    if isinstance(data, str):
        return data
    else:
        return data.decode('latin1')


def quote_header_value(value, extra_chars='', allow_token=True):
    """Quote a header value if necessary.

    :param value:
        The value to quote.
    :param extra_chars:
        A list of extra characters to skip quoting.
    :param allow_token:
        If this is enabled token values are returned unchanged.
    """
    if isinstance(value, bytes):
        value = bytes_to_wsgi(value)
    value = str(value)
    if allow_token:
        token_chars = _token_chars | set(extra_chars)
        if set(value).issubset(token_chars):
            return value
    return '"%s"' % value.replace('\\', '\\\\').replace('"', '\\"')


def unquote_header_value(value, is_filename=False):
    r"""Unquotes a header value.  (Reversal of :func:`quote_header_value`).
    This does not use the real unquoting but what browsers are actually
    using for quoting.

    :param value:
        The header value to unquote.
    """
    if value and value[0] == value[-1] == '"':
        # this is not the real unquoting, but fixing this so that the
        # RFC is met will result in bugs with internet explorer and
        # probably some other browsers as well.  IE for example is
        # uploading files with "C:\foo\bar.txt" as filename
        value = value[1:-1]

        # if this is a filename and the starting characters look like
        # a UNC path, then just return the value without quotes.  Using the
        # replace sequence below on a UNC path has the effect of turning
        # the leading double slash into a single slash and then
        # _fix_ie_filename() doesn't work correctly.  See #458.
        if not is_filename or value[:2] != '\\\\':
            return value.replace('\\\\', '\\').replace('\\"', '"')
    return value


def _options_header_vkw(value, kw):
    return dump_options_header(
        value, dict((k.replace('_', '-'), v) for k, v in kw.items())
    )


def unicodify_header_value(value):
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
        _value = unicodify_header_value(_value)
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
        _value = unicodify_header_value(_value)
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
            value = [(k, unicodify_header_value(v)) for (k, v) in value]
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


def dump_options_header(header, options):
    """The reverse function to :func:`parse_options_header`.

    :param header:
        The header to dump.
    :param options:
        A dict of options to append.
    """
    segments = []
    if header is not None:
        segments.append(header)
    for key, value in options.items():
        if value is None:
            segments.append(key)
        else:
            segments.append('%s=%s' % (key, quote_header_value(value)))
    return '; '.join(segments)


def dump_header(iterable, allow_token=True):
    """Dump an HTTP header again.  This is the reversal of
    :func:`parse_list_header`, :func:`parse_set_header` and
    :func:`parse_dict_header`.  This also quotes strings that include an
    equals sign unless you pass it as dict of key, value pairs.

    >>> dump_header({'foo': 'bar baz'})
    'foo="bar baz"'
    >>> dump_header(('foo', 'bar baz'))
    'foo, "bar baz"'

    :param iterable:
        The iterable or dict of values to quote.
    :param allow_token:
        If set to `False` tokens as values are disallowed.
        See :func:`quote_header_value` for more details.
    """
    if isinstance(iterable, dict):
        items = []
        for key, value in iterable.items():
            if value is None:
                items.append(key)
            else:
                items.append('%s=%s' % (
                    key,
                    quote_header_value(value, allow_token=allow_token)
                ))
    else:
        items = [quote_header_value(x, allow_token=allow_token)
                 for x in iterable]
    return ', '.join(items)


def parse_list_header(value):
    """Parse lists as described by RFC 2068 Section 2.

    In particular, parse comma-separated lists where the elements of
    the list may include quoted-strings.  A quoted-string could
    contain a comma.  A non-quoted string could have quotes in the
    middle.  Quotes are removed automatically after parsing.

    It basically works like :func:`parse_set_header` just that items
    may appear multiple times and case sensitivity is preserved.

    The return value is a standard :class:`list`:

    >>> parse_list_header('token, "quoted value"')
    ['token', 'quoted value']

    To create a header from the :class:`list` again, use the
    :func:`dump_header` function.

    :param value:
        A string with a list header.
    :return:
        :class:`list`
    """
    result = []
    for item in _parse_list_header(value):
        if item[:1] == item[-1:] == '"':
            item = unquote_header_value(item[1:-1])
        result.append(item)
    return result


def parse_dict_header(value, cls=dict):
    """Parse lists of key, value pairs as described by RFC 2068 Section 2 and
    convert them into a python dict (or any other mapping object created from
    the type with a dict like interface provided by the `cls` arugment):

    >>> d = parse_dict_header('foo="is a fish", bar="as well"')
    >>> type(d) is dict
    True
    >>> sorted(d.items())
    [('bar', 'as well'), ('foo', 'is a fish')]

    If there is no value for a key it will be `None`:

    >>> parse_dict_header('key_without_value')
    {'key_without_value': None}

    To create a header from the :class:`dict` again, use the
    :func:`dump_header` function.

    :param value:
        A string with a dict header.
    :param cls:
        Callable to use for storage of parsed results.
    :return:
        An instance of `cls`
    """
    result = cls()
    if not isinstance(value, str):
        # XXX: validate
        value = bytes_to_wsgi(value)
    for item in _parse_list_header(value):
        if '=' not in item:
            result[item] = None
            continue
        name, value = item.split('=', 1)
        if value[:1] == value[-1:] == '"':
            value = unquote_header_value(value[1:-1])
        result[name] = value
    return result


def parse_options_header(value):
    """Parse a ``Content-Type`` like header into a tuple with the content
    type and the options:

    >>> parse_options_header('text/html; charset=utf8')
    ('text/html', {'charset': 'utf8'})

    This should not be used to parse ``Cache-Control`` like headers that use
    a slightly different format.  For these headers use the
    :func:`parse_dict_header` function.

    :param value:
        The header to parse.
    :return:
        (str, options)
    """
    def _tokenize(string):
        for match in _option_header_piece_re.finditer(string):
            key, value = match.groups()
            key = unquote_header_value(key)
            if value is not None:
                value = unquote_header_value(value, key == 'filename')
            yield key, value

    if not value:
        return '', {}

    parts = _tokenize(';' + value)
    name = next(parts)[0]
    extra = dict(parts)
    return name, extra


class Accept(datastructures.ImmutableList):
    """An :class:`Accept` object is just a list subclass for lists of
    ``(value, quality)`` tuples.  It is automatically sorted by quality.

    All :class:`Accept` objects work similar to a list but provide extra
    functionality for working with the data.  Containment checks are
    normalized to the rules of that header:

    >>> a = CharsetAccept([('ISO-8859-1', 1), ('utf-8', 0.7)])
    >>> a.best
    'ISO-8859-1'
    >>> 'iso-8859-1' in a
    True
    >>> 'UTF8' in a
    True
    >>> 'utf7' in a
    False

    To get the quality for an item you can use normal item lookup:

    >>> print a['utf-8']
    0.7
    >>> a['utf7']
    0
    """

    def __init__(self, values=()):
        if values is None:
            list.__init__(self)
            self.provided = False
        elif isinstance(values, Accept):
            self.provided = values.provided
            list.__init__(self, values)
        else:
            self.provided = True
            values = [(a, b) for b, a in values]
            values.sort()
            values.reverse()
            list.__init__(self, [(a, b) for b, a in values])

    def _value_matches(self, value, item):
        """Check if a value matches a given accept item."""
        return item == '*' or item.lower() == value.lower()

    def __getitem__(self, key):
        """Besides index lookup (getting item n) you can also pass it a string
        to get the quality for the item.  If the item is not in the list, the
        returned quality is ``0``.
        """
        if isinstance(key, str):
            return self.quality(key)
        return list.__getitem__(self, key)

    def quality(self, key):
        """Returns the quality of the key.
        """
        for item, quality in self:
            if self._value_matches(key, item):
                return quality
        return 0

    def __contains__(self, value):
        for item, quality in self:
            if self._value_matches(value, item):
                return True
        return False

    def __repr__(self):
        return '%s([%s])' % (
            self.__class__.__name__,
            ', '.join('(%r, %s)' % (x, y) for x, y in self)
        )

    def index(self, key):
        """Get the position of an entry or raise :exc:`ValueError`.

        :param key:
            The key to be looked up.
        """
        if isinstance(key, str):
            for idx, (item, quality) in enumerate(self):
                if self._value_matches(key, item):
                    return idx
            raise ValueError(key)
        return list.index(self, key)

    def find(self, key):
        """Get the position of an entry or return -1.

        :param key:
            The key to be looked up.
        """
        try:
            return self.index(key)
        except ValueError:
            return -1

    def values(self):
        """Iterate over all values."""
        for item in self:
            yield item[0]

    def to_header(self):
        """Convert the header set into an HTTP header string."""
        result = []
        for value, quality in self:
            if quality != 1:
                value = '%s;q=%s' % (value, quality)
            result.append(value)
        return ','.join(result)

    def __str__(self):
        return self.to_header()

    def best_match(self, matches, default=None):
        """Returns the best match from a list of possible matches based
        on the quality of the client.  If two items have the same quality,
        the one is returned that comes first.

        :param matches:
            A list of matches to check for
        :param default:
            The value that is returned if none match
        """
        best_quality = -1
        result = default
        for server_item in matches:
            for client_item, quality in self:
                if quality <= best_quality:
                    break
                if self._value_matches(server_item, client_item) \
                   and quality > 0:
                    best_quality = quality
                    result = server_item
        return result

    @property
    def best(self):
        """The best match as value."""
        if self:
            return self[0][0]


class MIMEAccept(Accept):
    """Like :class:`Accept` but with special methods and behavior for
    mimetypes.
    """

    def _value_matches(self, value, item):
        def _normalize(x):
            x = x.lower()
            return x == '*' and ('*', '*') or x.split('/', 1)

        # this is from the application which is trusted.  to avoid developer
        # frustration we actually check these for valid values
        if '/' not in value:
            raise ValueError('invalid mimetype %r' % value)
        value_type, value_subtype = _normalize(value)
        if value_type == '*' and value_subtype != '*':
            raise ValueError('invalid mimetype %r' % value)

        if '/' not in item:
            return False
        item_type, item_subtype = _normalize(item)
        if item_type == '*' and item_subtype != '*':
            return False
        return (
            (item_type == item_subtype == '*' or
             value_type == value_subtype == '*') or
            (item_type == value_type and (item_subtype == '*' or
                                          value_subtype == '*' or
                                          item_subtype == value_subtype))
        )

    @property
    def accept_html(self):
        """True if this object accepts HTML."""
        return (
            'text/html' in self or
            'application/xhtml+xml' in self or
            self.accept_xhtml
        )

    @property
    def accept_xhtml(self):
        """True if this object accepts XHTML."""
        return (
            'application/xhtml+xml' in self or
            'application/xml' in self
        )

    @property
    def accept_json(self):
        """True if this object accepts JSON."""
        return 'application/json' in self


class LanguageAccept(Accept):
    """Like :class:`Accept` but with normalization for languages."""

    def _value_matches(self, value, item):
        def _normalize(language):
            return _locale_delim_re.split(language.lower())
        return item == '*' or _normalize(value) == _normalize(item)


class CharsetAccept(Accept):
    """Like :class:`Accept` but with normalization for charsets."""

    def _value_matches(self, value, item):
        def _normalize(name):
            try:
                return codecs.lookup(name).name
            except LookupError:
                return name.lower()
        return item == '*' or _normalize(value) == _normalize(item)


def parse_accept_header(value, cls=None):
    """Parses an HTTP Accept-* header.  This does not implement a complete
    valid algorithm but one that supports at least value and quality
    extraction.

    Returns a new :class:`Accept` object (basically a list of
    ``(value, quality)`` tuples sorted by the quality with some additional
    accessor methods).

    The second parameter can be a subclass of :class:`Accept` that is created
    with the parsed values and returned.

    :param value:
        The accept header string to be parsed.
    :param cls:
        The wrapper class for the return value (can be :class:`Accept` or a
        subclass thereof)
    :return:
        An instance of `cls`.
    """
    if cls is None:
        cls = Accept

    if not value:
        return cls(None)

    result = []
    for match in _accept_re.finditer(value):
        quality = match.group(2)
        if not quality:
            quality = 1
        else:
            quality = max(min(float(quality), 1), 0)
        result.append((match.group(1), quality))
    return cls(result)


def cache_property(key, empty, type):
    """Return a new property object for a cache header.  Useful if you
    want to add support for a cache extension in a subclass."""
    return property(lambda x: x._get_cache_value(key, empty, type),
                    lambda x, v: x._set_cache_value(key, v, type),
                    lambda x: x._del_cache_value(key),
                    'accessor for %r' % key)


class _CacheControl(datastructures.UpdateDictMixin, dict):
    """Subclass of a dict that stores values for a Cache-Control header.  It
    has accessors for all the cache-control directives specified in RFC 2616.
    The class does not differentiate between request and response directives.

    Because the cache-control directives in the HTTP header use dashes the
    python descriptors use underscores for that.

    To get a header of the :class:`CacheControl` object again you can convert
    the object into a string or call the :meth:`to_header` method.  If you plan
    to subclass it and add your own items have a look at the sourcecode for
    that class.
    """

    no_cache = cache_property('no-cache', '*', None)
    no_store = cache_property('no-store', None, bool)
    max_age = cache_property('max-age', -1, int)
    no_transform = cache_property('no-transform', None, None)

    def __init__(self, values=(), on_update=None):
        dict.__init__(self, values or ())
        self.on_update = on_update
        self.provided = values is not None

    def _get_cache_value(self, key, empty, type):
        """Used internally by the accessor properties."""
        if type is bool:
            return key in self
        if key in self:
            value = self[key]
            if value is None:
                return empty
            elif type is not None:
                try:
                    value = type(value)
                except ValueError:
                    pass
            return value

    def _set_cache_value(self, key, value, type):
        """Used internally by the accessor properties."""
        if type is bool:
            if value:
                self[key] = None
            else:
                self.pop(key, None)
        else:
            if value is None:
                self.pop(key)
            elif value is True:
                self[key] = None
            else:
                self[key] = value

    def _del_cache_value(self, key):
        """Used internally by the accessor properties."""
        if key in self:
            del self[key]

    def to_header(self):
        """Convert the stored values into a cache control header."""
        return dump_header(self)

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '<%s %s>' % (
            self.__class__.__name__,
            " ".join(
                "%s=%r" % (k, v) for k, v in sorted(self.items())
            ),
        )


class RequestCacheControl(datastructures.ImmutableDictMixin, _CacheControl):
    """A cache control for requests.  This is immutable and gives access
    to all the request-relevant cache control headers.

    To get a header of the :class:`RequestCacheControl` object again you can
    convert the object into a string or call the :meth:`to_header` method.  If
    you plan to subclass it and add your own items have a look at the
    sourcecode for that class.
    """

    max_stale = cache_property('max-stale', '*', int)
    min_fresh = cache_property('min-fresh', '*', int)
    no_transform = cache_property('no-transform', None, None)
    only_if_cached = cache_property('only-if-cached', None, bool)


class ResponseCacheControl(_CacheControl):
    """A cache control for responses.  Unlike :class:`RequestCacheControl`
    this is mutable and gives access to response-relevant cache control
    headers.

    To get a header of the :class:`ResponseCacheControl` object again you can
    convert the object into a string or call the :meth:`to_header` method.  If
    you plan to subclass it and add your own items have a look at the
    sourcecode for that class.
    """

    public = cache_property('public', None, bool)
    private = cache_property('private', '*', None)
    must_revalidate = cache_property('must-revalidate', None, bool)
    proxy_revalidate = cache_property('proxy-revalidate', None, bool)
    s_maxage = cache_property('s-maxage', None, None)


# attach cache_property to the _CacheControl as staticmethod
# so that others can reuse it.
_CacheControl.cache_property = staticmethod(cache_property)


def parse_cache_control_header(value, on_update=None, cls=None):
    """Parse a cache control header.  The RFC differs between response and
    request cache control, this method does not.  It's your responsibility
    to not use the wrong control statements.

    :param value:
        A cache control header to be parsed.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~verktyg.CacheControl` object is changed.
    :param cls:
        The class for the returned object.  By default
        :class:`~verktyg.RequestCacheControl` is used.
    :return:
        A `cls` object.
    """
    if cls is None:
        cls = RequestCacheControl
    if not value:
        return cls(None, on_update)
    return cls(parse_dict_header(value), on_update)


class HeaderSet(object):
    """Similar to the :class:`ETags` class this implements a set-like
    structure. Unlike :class:`ETags` this is case insensitive and used for
    vary, allow, and content-language headers.

    If not constructed using the :func:`parse_set_header` function the
    instantiation works like this:

    >>> hs = HeaderSet(['foo', 'bar', 'baz'])
    >>> hs
    HeaderSet(['foo', 'bar', 'baz'])
    """

    def __init__(self, headers=None, on_update=None):
        self._headers = list(headers or ())
        self._set = set([x.lower() for x in self._headers])
        self.on_update = on_update

    def add(self, header):
        """Add a new header to the set."""
        self.update((header,))

    def remove(self, header):
        """Remove a header from the set.  This raises an :exc:`KeyError` if the
        header is not in the set.

        :param header:
            The header to be removed.
        """
        key = header.lower()
        if key not in self._set:
            raise KeyError(header)
        self._set.remove(key)
        for idx, key in enumerate(self._headers):
            if key.lower() == header:
                del self._headers[idx]
                break
        if self.on_update is not None:
            self.on_update(self)

    def update(self, iterable):
        """Add all the headers from the iterable to the set.

        :param iterable:
            Updates the set with the items from the iterable.
        """
        inserted_any = False
        for header in iterable:
            key = header.lower()
            if key not in self._set:
                self._headers.append(header)
                self._set.add(key)
                inserted_any = True
        if inserted_any and self.on_update is not None:
            self.on_update(self)

    def discard(self, header):
        """Like :meth:`remove` but ignores errors.

        :param header:
            The header to be discarded.
        """
        try:
            return self.remove(header)
        except KeyError:
            pass

    def find(self, header):
        """Return the index of the header in the set or return -1 if not found.

        :param header:
            The header to be looked up.
        """
        header = header.lower()
        for idx, item in enumerate(self._headers):
            if item.lower() == header:
                return idx
        return -1

    def index(self, header):
        """Return the index of the header in the set or raise an
        :exc:`IndexError`.

        :param header:
            The header to be looked up.
        """
        rv = self.find(header)
        if rv < 0:
            raise IndexError(header)
        return rv

    def clear(self):
        """Clear the set."""
        self._set.clear()
        del self._headers[:]
        if self.on_update is not None:
            self.on_update(self)

    def as_set(self, preserve_casing=False):
        """Return the set as real python set type.  When calling this, all
        the items are converted to lowercase and the ordering is lost.

        :param preserve_casing:
            If set to `True` the items in the set returned will have the
            original case like in the :class:`HeaderSet`, otherwise they will
            be lowercase.
        """
        if preserve_casing:
            return set(self._headers)
        return set(self._set)

    def to_header(self):
        """Convert the header set into an HTTP header string."""
        return ', '.join(map(quote_header_value, self._headers))

    def __getitem__(self, idx):
        return self._headers[idx]

    def __delitem__(self, idx):
        rv = self._headers.pop(idx)
        self._set.remove(rv.lower())
        if self.on_update is not None:
            self.on_update(self)

    def __setitem__(self, idx, value):
        old = self._headers[idx]
        self._set.remove(old.lower())
        self._headers[idx] = value
        self._set.add(value.lower())
        if self.on_update is not None:
            self.on_update(self)

    def __contains__(self, header):
        return header.lower() in self._set

    def __len__(self):
        return len(self._set)

    def __iter__(self):
        return iter(self._headers)

    def __nonzero__(self):
        return bool(self._set)

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '%s(%r)' % (
            self.__class__.__name__,
            self._headers
        )


def parse_set_header(value, on_update=None):
    """Parse a set-like header and return a
    :class:`~werkzeug.datastructures.HeaderSet` object:

    >>> hs = parse_set_header('token, "quoted value"')

    The return value is an object that treats the items case-insensitively
    and keeps the order of the items:

    >>> 'TOKEN' in hs
    True
    >>> hs.index('quoted value')
    1
    >>> hs
    HeaderSet(['token', 'quoted value'])

    To create a header from the :class:`HeaderSet` again, use the
    :func:`dump_header` function.

    :param value:
        A set header to be parsed.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~werkzeug.datastructures.HeaderSet` object is changed.
    :return:
        A:class:`~werkzeug.datastructures.HeaderSet`
    """
    if not value:
        return HeaderSet(None, on_update)
    return HeaderSet(parse_list_header(value), on_update)


class Authorization(datastructures.ImmutableDictMixin, dict):
    """Represents an `Authorization` header sent by the client.  You should
    not create this kind of object yourself but use it when it's returned by
    the `parse_authorization_header` function.

    This object is a dict subclass and can be altered by setting dict items
    but it should be considered immutable as it's returned by the client and
    not meant for modifications.
    """

    def __init__(self, auth_type, data=None):
        dict.__init__(self, data or {})
        self.type = auth_type

    username = property(lambda x: x.get('username'), doc='''
        The username transmitted.  This is set for both basic and digest
        auth all the time.''')
    password = property(lambda x: x.get('password'), doc='''
        When the authentication type is basic this is the password
        transmitted by the client, else `None`.''')
    realm = property(lambda x: x.get('realm'), doc='''
        This is the server realm sent back for HTTP digest auth.''')
    nonce = property(lambda x: x.get('nonce'), doc='''
        The nonce the server sent for digest auth, sent back by the client.
        A nonce should be unique for every 401 response for HTTP digest
        auth.''')
    uri = property(lambda x: x.get('uri'), doc='''
        The URI from Request-URI of the Request-Line; duplicated because
        proxies are allowed to change the Request-Line in transit.  HTTP
        digest auth only.''')
    nc = property(lambda x: x.get('nc'), doc='''
        The nonce count value transmitted by clients if a qop-header is
        also transmitted.  HTTP digest auth only.''')
    cnonce = property(lambda x: x.get('cnonce'), doc='''
        If the server sent a qop-header in the ``WWW-Authenticate``
        header, the client has to provide this value for HTTP digest auth.
        See the RFC for more details.''')
    response = property(lambda x: x.get('response'), doc='''
        A string of 32 hex digits computed as defined in RFC 2617, which
        proves that the user knows a password.  Digest auth only.''')
    opaque = property(lambda x: x.get('opaque'), doc='''
        The opaque header from the server returned unchanged by the client.
        It is recommended that this string be base64 or hexadecimal data.
        Digest auth only.''')

    @property
    def qop(self):
        """Indicates what "quality of protection" the client has applied to
        the message for HTTP digest auth."""
        def on_update(header_set):
            if not header_set and 'qop' in self:
                del self['qop']
            elif header_set:
                self['qop'] = header_set.to_header()
        return parse_set_header(self.get('qop'), on_update)


def parse_authorization_header(value):
    """Parse an HTTP basic/digest authorization header transmitted by the web
    browser.  The return value is either `None` if the header was invalid or
    not given, otherwise an :class:`~Authorization`
    object.

    :param value:
        The authorization header to parse.
    :return:
        A:class:`~Authorization` object or `None`.
    """
    if not value:
        return
    value = wsgi_to_bytes(value)
    try:
        auth_type, auth_info = value.split(None, 1)
        auth_type = auth_type.lower()
    except ValueError:
        return
    if auth_type == b'basic':
        try:
            username, password = base64.b64decode(auth_info).split(b':', 1)
        except Exception:
            return
        return Authorization('basic', {'username':  bytes_to_wsgi(username),
                                       'password': bytes_to_wsgi(password)})
    elif auth_type == b'digest':
        auth_map = parse_dict_header(auth_info)
        for key in 'username', 'realm', 'nonce', 'uri', 'response':
            if key not in auth_map:
                return
        if 'qop' in auth_map:
            if not auth_map.get('nc') or not auth_map.get('cnonce'):
                return
        return Authorization('digest', auth_map)


def auth_property(name, doc=None):
    """A static helper function for subclasses to add extra authentication
    system properties onto a class::

        class FooAuthenticate(WWWAuthenticate):
            special_realm = auth_property('special_realm')

    For more information have a look at the sourcecode to see how the
    regular properties (:attr:`realm` etc.) are implemented.
    """

    def _set_value(self, value):
        if value is None:
            self.pop(name, None)
        else:
            self[name] = str(value)
    return property(lambda x: x.get(name), _set_value, doc=doc)


class WWWAuthenticate(datastructures.UpdateDictMixin, dict):
    """Provides simple access to `WWW-Authenticate` headers."""

    #: list of keys that require quoting in the generated header
    _require_quoting = frozenset(['domain', 'nonce', 'opaque', 'realm', 'qop'])

    def __init__(self, auth_type=None, values=None, on_update=None):
        dict.__init__(self, values or ())
        if auth_type:
            self['__auth_type__'] = auth_type
        self.on_update = on_update

    def set_basic(self, realm='authentication required'):
        """Clear the auth info and enable basic auth."""
        dict.clear(self)
        dict.update(self, {'__auth_type__': 'basic', 'realm': realm})
        if self.on_update:
            self.on_update(self)

    def set_digest(self, realm, nonce, qop=('auth',), opaque=None,
                   algorithm=None, stale=False):
        """Clear the auth info and enable digest auth."""
        d = {
            '__auth_type__':    'digest',
            'realm':            realm,
            'nonce':            nonce,
            'qop':              dump_header(qop)
        }
        if stale:
            d['stale'] = 'TRUE'
        if opaque is not None:
            d['opaque'] = opaque
        if algorithm is not None:
            d['algorithm'] = algorithm
        dict.clear(self)
        dict.update(self, d)
        if self.on_update:
            self.on_update(self)

    def to_header(self):
        """Convert the stored values into a WWW-Authenticate header."""
        d = dict(self)
        auth_type = d.pop('__auth_type__', None) or 'basic'
        return '%s %s' % (auth_type.title(), ', '.join([
            '%s=%s' % (key, quote_header_value(
                value, allow_token=key not in self._require_quoting
            ))
            for key, value in d.items()
        ]))

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '<%s %r>' % (
            self.__class__.__name__,
            self.to_header()
        )

    def _set_property(name, doc=None):
        def fget(self):
            def on_update(header_set):
                if not header_set and name in self:
                    del self[name]
                elif header_set:
                    self[name] = header_set.to_header()
            return parse_set_header(self.get(name), on_update)
        return property(fget, doc=doc)

    type = auth_property('__auth_type__', doc='''
        The type of the auth mechanism.  HTTP currently specifies
        `Basic` and `Digest`.''')
    realm = auth_property('realm', doc='''
        A string to be displayed to users so they know which username and
        password to use.  This string should contain at least the name of
        the host performing the authentication and might additionally
        indicate the collection of users who might have access.''')
    domain = _set_property('domain', doc='''
        A list of URIs that define the protection space.  If a URI is an
        absolute path, it is relative to the canonical root URL of the
        server being accessed.''')
    nonce = auth_property('nonce', doc='''
        A server-specified data string which should be uniquely generated
        each time a 401 response is made.  It is recommended that this
        string be base64 or hexadecimal data.''')
    opaque = auth_property('opaque', doc='''
        A string of data, specified by the server, which should be returned
        by the client unchanged in the Authorization header of subsequent
        requests with URIs in the same protection space.  It is recommended
        that this string be base64 or hexadecimal data.''')
    algorithm = auth_property('algorithm', doc='''
        A string indicating a pair of algorithms used to produce the digest
        and a checksum.  If this is not present it is assumed to be "MD5".
        If the algorithm is not understood, the challenge should be ignored
        (and a different one used, if there is more than one).''')
    qop = _set_property('qop', doc='''
        A set of quality-of-privacy directives such as auth and auth-int.''')

    def _get_stale(self):
        val = self.get('stale')
        if val is not None:
            return val.lower() == 'true'

    def _set_stale(self, value):
        if value is None:
            self.pop('stale', None)
        else:
            self['stale'] = value and 'TRUE' or 'FALSE'
    stale = property(_get_stale, _set_stale, doc='''
        A flag, indicating that the previous request from the client was
        rejected because the nonce value was stale.''')
    del _get_stale, _set_stale
    del _set_property


# make auth_property a staticmethod so that subclasses of
# `WWWAuthenticate` can use it for new properties.
WWWAuthenticate.auth_property = staticmethod(auth_property)


def parse_www_authenticate_header(value, on_update=None):
    """Parse an HTTP WWW-Authenticate header into a
    :class:`~werkzeug.datastructures.WWWAuthenticate` object.

    :param value:
        A WWW-Authenticate header to parse.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~werkzeug.datastructures.WWWAuthenticate` object is changed.
    :return:
        A:class:`~werkzeug.datastructures.WWWAuthenticate` object.
    """
    if not value:
        return WWWAuthenticate(on_update=on_update)
    try:
        auth_type, auth_info = value.split(None, 1)
        auth_type = auth_type.lower()
    except (ValueError, AttributeError):
        return WWWAuthenticate(value.strip().lower(), on_update=on_update)
    return WWWAuthenticate(auth_type, parse_dict_header(auth_info),
                           on_update)


class IfRange(object):
    """Very simple object that represents the `If-Range` header in parsed
    form.  It will either have neither a etag or date or one of either but
    never both.
    """

    def __init__(self, etag=None, date=None):
        #: The etag parsed and unquoted.  Ranges always operate on strong
        #: etags so the weakness information is not necessary.
        self.etag = etag
        #: The date in parsed format or `None`.
        self.date = date

    def to_header(self):
        """Converts the object back into an HTTP header."""
        if self.date is not None:
            return http_date(self.date)
        if self.etag is not None:
            return quote_etag(self.etag)
        return ''

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, str(self))


def parse_if_range_header(value):
    """Parses an if-range header which can be an etag or a date.  Returns
    a :class:`~werkzeug.datastructures.IfRange` object.
    """
    if not value:
        return IfRange()
    date = parse_date(value)
    if date is not None:
        return IfRange(date=date)
    # drop weakness information
    return IfRange(unquote_etag(value)[0])


class Range(object):
    """Represents a range header.  All the methods are only supporting bytes
    as unit.  It does store multiple ranges but :meth:`range_for_length` will
    only work if only one range is provided.
    """

    def __init__(self, units, ranges):
        #: The units of this range.  Usually "bytes".
        self.units = units
        #: A list of ``(begin, end)`` tuples for the range header provided.
        #: The ranges are non-inclusive.
        self.ranges = ranges

    def range_for_length(self, length):
        """If the range is for bytes, the length is not None and there is
        exactly one range and it is satisfiable it returns a ``(start, stop)``
        tuple, otherwise `None`.
        """
        if self.units != 'bytes' or length is None or len(self.ranges) != 1:
            return None
        start, end = self.ranges[0]
        if end is None:
            end = length
            if start < 0:
                start += length
        if is_byte_range_valid(start, end, length):
            return start, min(end, length)

    def make_content_range(self, length):
        """Creates a :class:`~verktyg.datastructures.ContentRange` object
        from the current range and given content length.
        """
        rng = self.range_for_length(length)
        if rng is not None:
            return ContentRange(self.units, rng[0], rng[1], length)

    def to_header(self):
        """Converts the object back into an HTTP header."""
        ranges = []
        for begin, end in self.ranges:
            if end is None:
                ranges.append(begin >= 0 and '%s-' % begin or str(begin))
            else:
                ranges.append('%s-%s' % (begin, end - 1))
        return '%s=%s' % (self.units, ','.join(ranges))

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, str(self))


def parse_range_header(value, make_inclusive=True):
    """Parses a range header into a :class:`~werkzeug.datastructures.Range`
    object.  If the header is missing or malformed `None` is returned.
    `ranges` is a list of ``(start, stop)`` tuples where the ranges are
    non-inclusive.
    """
    if not value or '=' not in value:
        return None

    ranges = []
    last_end = 0
    units, rng = value.split('=', 1)
    units = units.strip().lower()

    for item in rng.split(','):
        item = item.strip()
        if '-' not in item:
            return None
        if item.startswith('-'):
            if last_end < 0:
                return None
            begin = int(item)
            end = None
            last_end = -1
        elif '-' in item:
            begin, end = item.split('-', 1)
            begin = int(begin)
            if begin < last_end or last_end < 0:
                return None
            if end:
                end = int(end) + 1
                if begin >= end:
                    return None
            else:
                end = None
            last_end = end
        ranges.append((begin, end))

    return Range(units, ranges)


class ContentRange(object):
    """Represents the content range header.
    """

    def __init__(self, units, start, stop, length=None, on_update=None):
        assert is_byte_range_valid(start, stop, length), \
            'Bad range provided'
        self.on_update = on_update
        self.set(start, stop, length, units)

    def _callback_property(name):
        def fget(self):
            return getattr(self, name)

        def fset(self, value):
            setattr(self, name, value)
            if self.on_update is not None:
                self.on_update(self)
        return property(fget, fset)

    #: The units to use, usually "bytes"
    units = _callback_property('_units')
    #: The start point of the range or `None`.
    start = _callback_property('_start')
    #: The stop point of the range (non-inclusive) or `None`.  Can only be
    #: `None` if also start is `None`.
    stop = _callback_property('_stop')
    #: The length of the range or `None`.
    length = _callback_property('_length')

    def set(self, start, stop, length=None, units='bytes'):
        """Simple method to update the ranges."""
        assert is_byte_range_valid(start, stop, length), \
            'Bad range provided'
        self._units = units
        self._start = start
        self._stop = stop
        self._length = length
        if self.on_update is not None:
            self.on_update(self)

    def unset(self):
        """Sets the units to `None` which indicates that the header should
        no longer be used.
        """
        self.set(None, None, units=None)

    def to_header(self):
        if self.units is None:
            return ''
        if self.length is None:
            length = '*'
        else:
            length = self.length
        if self.start is None:
            return '%s */%s' % (self.units, length)
        return '%s %s-%s/%s' % (
            self.units,
            self.start,
            self.stop - 1,
            length
        )

    def __nonzero__(self):
        return self.units is not None

    __bool__ = __nonzero__

    def __str__(self):
        return self.to_header()

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, str(self))


def parse_content_range_header(value, on_update=None):
    """Parses a range header into a
    :class:`~werkzeug.datastructures.ContentRange` object or `None` if
    parsing is not possible.

    :param value:
        A content range header to be parsed.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~werkzeug.datastructures.ContentRange` object is changed.
    """
    if value is None:
        return None
    try:
        units, rangedef = (value or '').strip().split(None, 1)
    except ValueError:
        return None

    if '/' not in rangedef:
        return None
    rng, length = rangedef.split('/', 1)
    if length == '*':
        length = None
    elif length.isdigit():
        length = int(length)
    else:
        return None

    if rng == '*':
        return ContentRange(units, None, None, length, on_update=on_update)
    elif '-' not in rng:
        return None

    start, stop = rng.split('-', 1)
    try:
        start = int(start)
        stop = int(stop) + 1
    except ValueError:
        return None

    if is_byte_range_valid(start, stop, length):
        return ContentRange(units, start, stop, length, on_update=on_update)


def quote_etag(etag, weak=False):
    """Quote an etag.

    :param etag:
        The etag to quote.
    :param weak:
        Set to `True` to tag it "weak".
    """
    if '"' in etag:
        raise ValueError('invalid etag')
    etag = '"%s"' % etag
    if weak:
        etag = 'w/' + etag
    return etag


def unquote_etag(etag):
    """Unquote a single etag:

    >>> unquote_etag('w/"bar"')
    ('bar', True)
    >>> unquote_etag('"bar"')
    ('bar', False)

    :param etag:
        The etag identifier to unquote.
    :return:
        An ``(etag, weak)`` tuple.
    """
    if not etag:
        return None, None
    etag = etag.strip()
    weak = False
    if etag[:2] in ('w/', 'W/'):
        weak = True
        etag = etag[2:]
    if etag[:1] == etag[-1:] == '"':
        etag = etag[1:-1]
    return etag, weak


class ETags(object):
    """A set that can be used to check if one etag is present in a collection
    of etags.
    """

    def __init__(self, strong_etags=None, weak_etags=None, star_tag=False):
        self._strong = frozenset(not star_tag and strong_etags or ())
        self._weak = frozenset(weak_etags or ())
        self.star_tag = star_tag

    def as_set(self, include_weak=False):
        """Convert the `ETags` object into a python set.  Per default all the
        weak etags are not part of this set."""
        rv = set(self._strong)
        if include_weak:
            rv.update(self._weak)
        return rv

    def is_weak(self, etag):
        """Check if an etag is weak."""
        return etag in self._weak

    def contains_weak(self, etag):
        """Check if an etag is part of the set including weak and strong tags.
        """
        return self.is_weak(etag) or self.contains(etag)

    def contains(self, etag):
        """Check if an etag is part of the set ignoring weak tags.
        It is also possible to use the ``in`` operator.

        """
        if self.star_tag:
            return True
        return etag in self._strong

    def contains_raw(self, etag):
        """When passed a quoted tag it will check if this tag is part of the
        set.  If the tag is weak it is checked against weak and strong tags,
        otherwise strong only."""
        etag, weak = unquote_etag(etag)
        if weak:
            return self.contains_weak(etag)
        return self.contains(etag)

    def to_header(self):
        """Convert the etags set into a HTTP header string."""
        if self.star_tag:
            return '*'
        return ', '.join(
            ['"%s"' % x for x in self._strong] +
            ['w/"%s"' % x for x in self._weak]
        )

    def __call__(self, etag=None, data=None, include_weak=False):
        if [etag, data].count(None) != 1:
            raise TypeError('either tag or data required, but at least one')
        if etag is None:
            etag = generate_etag(data)
        if include_weak:
            if etag in self._weak:
                return True
        return etag in self._strong

    def __bool__(self):
        return bool(self.star_tag or self._strong or self._weak)

    __nonzero__ = __bool__

    def __str__(self):
        return self.to_header()

    def __iter__(self):
        return iter(self._strong)

    def __contains__(self, etag):
        return self.contains(etag)

    def __repr__(self):
        return '<%s %r>' % (self.__class__.__name__, str(self))


def parse_etags(value):
    """Parse an etag header.

    :param value:
        The tag header to parse
    :return:
        An :class:`~werkzeug.datastructures.ETags` object.
    """
    if not value:
        return ETags()
    strong = []
    weak = []
    end = len(value)
    pos = 0
    while pos < end:
        match = _etag_re.match(value, pos)
        if match is None:
            break
        is_weak, quoted, raw = match.groups()
        if raw == '*':
            return ETags(star_tag=True)
        elif quoted:
            raw = quoted
        if is_weak:
            weak.append(raw)
        else:
            strong.append(raw)
        pos = match.end()
    return ETags(strong, weak)


def generate_etag(data):
    """Generate an etag for some data."""
    return md5(data).hexdigest()


def parse_date(value):
    """Parse one of the following date formats into a datetime object:

    .. sourcecode:: text

        Sun, 06 Nov 1994 08:49:37 GMT  ; RFC 822, updated by RFC 1123
        Sunday, 06-Nov-94 08:49:37 GMT ; RFC 850, obsoleted by RFC 1036
        Sun Nov  6 08:49:37 1994       ; ANSI C's asctime() format

    If parsing fails the return value is `None`.

    :param value:
        A string with a supported date format.
    :return:
        A :class:`datetime.datetime` object.
    """
    if value:
        t = parsedate_tz(value.strip())
        if t is not None:
            try:
                year = t[0]
                # unfortunately that function does not tell us if two digit
                # years were part of the string, or if they were prefixed
                # with two zeroes.  So what we do is to assume that 69-99
                # refer to 1900, and everything below to 2000
                if year >= 0 and year <= 68:
                    year += 2000
                elif year >= 69 and year <= 99:
                    year += 1900
                return datetime(*((year,) + t[1:7])) - \
                    timedelta(seconds=t[-1] or 0)
            except (ValueError, OverflowError):
                return None


def _dump_date(d, delim):
    """Used for `http_date` and `cookie_date`."""
    if d is None:
        d = gmtime()
    elif isinstance(d, datetime):
        d = d.utctimetuple()
    elif isinstance(d, (int, float)):
        d = gmtime(d)
    return '%s, %02d%s%s%s%s %02d:%02d:%02d GMT' % (
        ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')[d.tm_wday],
        d.tm_mday, delim,
        ('Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep',
         'Oct', 'Nov', 'Dec')[d.tm_mon - 1],
        delim, str(d.tm_year), d.tm_hour, d.tm_min, d.tm_sec
    )


def cookie_date(expires=None):
    """Formats the time to ensure compatibility with Netscape's cookie
    standard.

    Accepts a floating point number expressed in seconds since the epoch in, a
    datetime object or a timetuple.  All times in UTC.  The :func:`parse_date`
    function can be used to parse such a date.

    Outputs a string in the format ``Wdy, DD-Mon-YYYY HH:MM:SS GMT``.

    :param expires:
        If provided that date is used, otherwise the current.
    """
    return _dump_date(expires, '-')


def http_date(timestamp=None):
    """Formats the time to match the RFC1123 date format.

    Accepts a floating point number expressed in seconds since the epoch in, a
    datetime object or a timetuple.  All times in UTC.  The :func:`parse_date`
    function can be used to parse such a date.

    Outputs a string in the format ``Wdy, DD Mon YYYY HH:MM:SS GMT``.

    :param timestamp:
        If provided that date is used, otherwise the current.
    """
    return _dump_date(timestamp, ' ')


def is_resource_modified(environ, etag=None, data=None, last_modified=None):
    """Convenience method for conditional requests.

    :param environ:
        The WSGI environment of the request to be checked.
    :param etag:
        The etag for the response for comparison.
    :param data:
        Or alternatively the data of the response to automatically generate an
        etag using :func:`generate_etag`.
    :param last_modified:
        An optional date of the last modification.
    :return:
        `True` if the resource was modified, otherwise `False`.
    """
    if etag is None and data is not None:
        etag = generate_etag(data)
    elif data is not None:
        raise TypeError('both data and etag given')
    if environ['REQUEST_METHOD'] not in ('GET', 'HEAD'):
        return False

    unmodified = False
    if isinstance(last_modified, str):
        last_modified = parse_date(last_modified)

    # ensure that microsecond is zero because the HTTP spec does not transmit
    # that either and we might have some false positives.  See issue #39
    if last_modified is not None:
        last_modified = last_modified.replace(microsecond=0)

    modified_since = parse_date(environ.get('HTTP_IF_MODIFIED_SINCE'))

    if modified_since and last_modified and last_modified <= modified_since:
        unmodified = True
    if etag:
        if_none_match = parse_etags(environ.get('HTTP_IF_NONE_MATCH'))
        if if_none_match:
            unmodified = if_none_match.contains_raw(etag)

    return not unmodified


def remove_entity_headers(headers, allowed=('expires', 'content-location')):
    """Remove all entity headers from a list or :class:`Headers` object.  This
    operation works in-place.  `Expires` and `Content-Location` headers are
    by default not removed.  The reason for this is :rfc:`2616` section
    10.3.5 which specifies some entity headers that should be sent.

    :param headers:
        A list or :class:`Headers` object.
    :param allowed:
        A list of headers that should still be allowed even though they are
        entity headers.
    """
    allowed = set(x.lower() for x in allowed)
    headers[:] = [(key, value) for key, value in headers if
                  not is_entity_header(key) or key.lower() in allowed]


def remove_hop_by_hop_headers(headers):
    """Remove all HTTP/1.1 "Hop-by-Hop" headers from a list or
    :class:`Headers` object.  This operation works in-place.

    :param headers:
        A list or :class:`Headers` object.
    """
    headers[:] = [(key, value) for key, value in headers if
                  not is_hop_by_hop_header(key)]


def is_entity_header(header):
    """Check if a header is an entity header.

    :param header:
        The header to test.
    :return:
        `True` if it's an entity header, `False` otherwise.
    """
    return header.lower() in _entity_headers


def is_hop_by_hop_header(header):
    """Check if a header is an HTTP/1.1 "Hop-by-Hop" header.

    :param header:
        The header to test.
    :return:
        `True` if it's an entity header, `False` otherwise.
    """
    return header.lower() in _hop_by_hop_headers


def parse_cookie(header, charset='utf-8', errors='replace', cls=None):
    """Parse a cookie.  Either from a string or WSGI environ.

    Per default encoding errors are ignored.  If you want a different behavior
    you can set `errors` to ``'replace'`` or ``'strict'``.  In strict mode a
    :exc:`HTTPUnicodeError` is raised.

    :param header:
        The header to be used to parse the cookie.  Alternatively this can be a
        WSGI environment.
    :param charset:
        The charset for the cookie values.
    :param errors:
        The error behavior for the charset decoding.
    :param cls:
        An optional dict class to use.  If this is not specified or `None` the
        default :class:`TypeConversionDict` is used.
    """
    if isinstance(header, dict):
        header = header.get('HTTP_COOKIE', '')
    elif header is None:
        header = ''

    # If the value is an unicode string it's mangled through latin1.  This
    # is done because on PEP 3333 on Python 3 all headers are assumed latin1
    # which however is incorrect for cookies, which are sent in page encoding.
    # As a result we
    if isinstance(header, str):
        header = header.encode('latin1', 'replace')

    if cls is None:
        cls = datastructures.TypeConversionDict

    def _parse_pairs():
        for key, val in _cookie_parse_impl(header):
            key = to_unicode(key, charset, errors, allow_none_charset=True)
            val = to_unicode(val, charset, errors, allow_none_charset=True)
            yield key, val

    return cls(_parse_pairs())


def dump_cookie(key, value='', max_age=None, expires=None, path='/',
                domain=None, secure=False, httponly=False,
                charset='utf-8', sync_expires=True):
    """Creates a new Set-Cookie header without the ``Set-Cookie`` prefix
    The parameters are the same as in the cookie Morsel object in the
    Python standard library but it accepts unicode data, too.

    On Python 3 the return value of this function will be a unicode
    string, on Python 2 it will be a native string.  In both cases the
    return value is usually restricted to ascii as the vast majority of
    values are properly escaped, but that is no guarantee.  If a unicode
    string is returned it's tunneled through latin1 as required by
    PEP 3333.

    The return value is not ASCII safe if the key contains unicode
    characters.  This is technically against the specification but
    happens in the wild.  It's strongly recommended to not use
    non-ASCII values for the keys.

    :param max_age:
        Should be a number of seconds, or `None` (default) if the cookie should
        last only as long as the client's browser session.  Additionally
        `timedelta` objects are accepted, too.
    :param expires:
        Should be a `datetime` object or unix timestamp.
    :param path:
        Limits the cookie to a given path, per default it will span the whole
        domain.
    :param domain:
        Use this if you want to set a cross-domain cookie. For example,
        ``domain=".example.com"`` will set a cookie that is readable by the
        domain ``www.example.com``, ``foo.example.com`` etc. Otherwise, a
        cookie will only be readable by the domain that set it.
    :param secure:
        The cookie will only be available via HTTPS.
    :param httponly:
        Disallow JavaScript to access the cookie.  This is an extension to the
        cookie standard and probably not supported by all browsers.
    :param charset:
        The encoding for unicode values.
    :param sync_expires:
        Automatically set expires if max_age is defined but expires not.
    """
    key = to_bytes(key, charset)
    value = to_bytes(value, charset)

    if path is not None:
        path = iri_to_uri(path, charset)
    domain = _make_cookie_domain(domain)
    if isinstance(max_age, timedelta):
        max_age = (max_age.days * 60 * 60 * 24) + max_age.seconds
    if expires is not None:
        if not isinstance(expires, str):
            expires = cookie_date(expires)
    elif max_age is not None and sync_expires:
        expires = to_bytes(cookie_date(time() + max_age))

    buf = [key + b'=' + _cookie_quote(value)]

    # XXX: In theory all of these parameters that are not marked with `None`
    # should be quoted.  Because stdlib did not quote it before I did not
    # want to introduce quoting there now.
    for k, v, q in ((b'Domain', domain, True),
                    (b'Expires', expires, False,),
                    (b'Max-Age', max_age, False),
                    (b'Secure', secure, None),
                    (b'HttpOnly', httponly, None),
                    (b'Path', path, False)):
        if q is None:
            if v:
                buf.append(k)
            continue

        if v is None:
            continue

        tmp = bytearray(k)
        if not isinstance(v, (bytes, bytearray)):
            v = to_bytes(str(v), charset)
        if q:
            v = _cookie_quote(v)
        tmp += b'=' + v
        buf.append(bytes(tmp))

    # The return value will be an incorrectly encoded latin1 header on
    # Python 3 for consistency with the headers object and a bytestring
    # on Python 2 because that's how the API makes more sense.
    rv = b'; '.join(buf)
    rv = rv.decode('latin1')
    return rv


def is_byte_range_valid(start, stop, length):
    """Checks if a given byte content range is valid for the given length.
    """
    if (start is None) != (stop is None):
        return False
    elif start is None:
        return length is None or length >= 0
    elif length is None:
        return 0 <= start < stop
    elif start >= stop:
        return False
    return 0 <= start < length


class FileStorage(object):
    """The :class:`FileStorage` class is a thin wrapper over incoming files.
    It is used by the request object to represent uploaded files.  All the
    attributes of the wrapper stream are proxied by the file storage so
    it's possible to do ``storage.read()`` instead of the long form
    ``storage.stream.read()``.
    """

    def __init__(self, stream=None, filename=None, name=None,
                 content_type=None, content_length=None,
                 headers=None):
        self.name = name
        self.stream = stream or _empty_stream

        # if no filename is provided we can attempt to get the filename
        # from the stream object passed.  There we have to be careful to
        # skip things like <fdopen>, <stderr> etc.  Python marks these
        # special filenames with angular brackets.
        if filename is None:
            filename = getattr(stream, 'name', None)
            s = make_literal_wrapper(filename)
            if filename and filename[0] == s('<') and filename[-1] == s('>'):
                filename = None

            # On Python 3 we want to make sure the filename is always unicode.
            # This might not be if the name attribute is bytes due to the
            # file being opened from the bytes API.
            if isinstance(filename, bytes):
                filename = filename.decode(sys.getfilesystemencoding(),
                                           'replace')

        self.filename = filename
        if headers is None:
            headers = Headers()
        self.headers = headers
        if content_type is not None:
            headers['Content-Type'] = content_type
        if content_length is not None:
            headers['Content-Length'] = str(content_length)

    def _parse_content_type(self):
        if not hasattr(self, '_parsed_content_type'):
            self._parsed_content_type = \
                parse_options_header(self.content_type)

    @property
    def content_type(self):
        """The content-type sent in the header.  Usually not available"""
        return self.headers.get('content-type')

    @property
    def content_length(self):
        """The content-length sent in the header.  Usually not available"""
        return int(self.headers.get('content-length') or 0)

    @property
    def mimetype(self):
        """Like :attr:`content_type`, but without parameters (eg, without
        charset, type etc.) and always lowercase.  For example if the content
        type is ``text/HTML; charset=utf-8`` the mimetype would be
        ``'text/html'``.
        """
        self._parse_content_type()
        return self._parsed_content_type[0].lower()

    @property
    def mimetype_params(self):
        """The mimetype parameters as dict.  For example if the content
        type is ``text/html; charset=utf-8`` the params would be
        ``{'charset': 'utf-8'}``.
        """
        self._parse_content_type()
        return self._parsed_content_type[1]

    def save(self, dst, buffer_size=16384):
        """Save the file to a destination path or file object.  If the
        destination is a file object you have to close it yourself after the
        call.  The buffer size is the number of bytes held in memory during
        the copy process.  It defaults to 16KB.

        For secure file saving also have a look at :func:`secure_filename`.

        :param dst:
            A filename or open file object the uploaded file is saved to.
        :param buffer_size:
            The size of the buffer.  This works the same as the `length`
            parameter of :func:`shutil.copyfileobj`.
        """
        from shutil import copyfileobj
        close_dst = False
        if isinstance(dst, str):
            dst = open(dst, 'wb')
            close_dst = True
        try:
            copyfileobj(self.stream, dst, buffer_size)
        finally:
            if close_dst:
                dst.close()

    def close(self):
        """Close the underlying file if possible."""
        try:
            self.stream.close()
        except Exception:
            pass

    def __nonzero__(self):
        return bool(self.filename)
    __bool__ = __nonzero__

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __iter__(self):
        return iter(self.readline, '')

    def __repr__(self):
        return '<%s: %r (%r)>' % (
            self.__class__.__name__,
            self.filename,
            self.content_type
        )
