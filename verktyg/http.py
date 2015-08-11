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
from time import time, gmtime
from email.utils import parsedate_tz
from urllib.request import parse_http_list as _parse_list_header
from datetime import datetime, timedelta
from hashlib import md5
import base64

from werkzeug._internal import (
    _cookie_quote, _make_cookie_domain, _cookie_parse_impl,
)
from werkzeug._compat import to_unicode, to_bytes


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


HTTP_STATUS_CODES = {
    100:    'Continue',
    101:    'Switching Protocols',
    102:    'Processing',
    200:    'OK',
    201:    'Created',
    202:    'Accepted',
    203:    'Non Authoritative Information',
    204:    'No Content',
    205:    'Reset Content',
    206:    'Partial Content',
    207:    'Multi Status',
    226:    'IM Used',              # see RFC 3229
    300:    'Multiple Choices',
    301:    'Moved Permanently',
    302:    'Found',
    303:    'See Other',
    304:    'Not Modified',
    305:    'Use Proxy',
    307:    'Temporary Redirect',
    400:    'Bad Request',
    401:    'Unauthorized',
    402:    'Payment Required',     # unused
    403:    'Forbidden',
    404:    'Not Found',
    405:    'Method Not Allowed',
    406:    'Not Acceptable',
    407:    'Proxy Authentication Required',
    408:    'Request Timeout',
    409:    'Conflict',
    410:    'Gone',
    411:    'Length Required',
    412:    'Precondition Failed',
    413:    'Request Entity Too Large',
    414:    'Request URI Too Long',
    415:    'Unsupported Media Type',
    416:    'Requested Range Not Satisfiable',
    417:    'Expectation Failed',
    418:    'I\'m a teapot',  # see RFC 2324
    422:    'Unprocessable Entity',
    423:    'Locked',
    424:    'Failed Dependency',
    426:    'Upgrade Required',
    428:    'Precondition Required',  # see RFC 6585
    429:    'Too Many Requests',
    431:    'Request Header Fields Too Large',
    449:    'Retry With',  # proprietary MS extension
    500:    'Internal Server Error',
    501:    'Not Implemented',
    502:    'Bad Gateway',
    503:    'Service Unavailable',
    504:    'Gateway Timeout',
    505:    'HTTP Version Not Supported',
    507:    'Insufficient Storage',
    510:    'Not Extended'
}


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


def parse_cache_control_header(value, on_update=None, cls=None):
    """Parse a cache control header.  The RFC differs between response and
    request cache control, this method does not.  It's your responsibility
    to not use the wrong control statements.

    :param value:
        A cache control header to be parsed.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~werkzeug.datastructures.CacheControl` object is changed.
    :param cls:
        The class for the returned object.  By default
        :class:`~werkzeug.datastructures.RequestCacheControl` is used.
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


def parse_authorization_header(value):
    """Parse an HTTP basic/digest authorization header transmitted by the web
    browser.  The return value is either `None` if the header was invalid or
    not given, otherwise an :class:`~werkzeug.datastructures.Authorization`
    object.

    :param value:
        The authorization header to parse.
    :return:
        A:class:`~werkzeug.datastructures.Authorization` object or `None`.
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
        cls = TypeConversionDict

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


# circular dependency fun
from werkzeug.datastructures import Accept, ETags, Authorization, \
    WWWAuthenticate, TypeConversionDict, IfRange, Range, ContentRange, \
    RequestCacheControl

from werkzeug.urls import iri_to_uri
