"""
    verktyg.http.cookies
    ~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import re
import string
from itertools import chain
from time import time
from datetime import timedelta

from werkzeug._internal import _encode_idna

from verktyg.urls import iri_to_uri
from verktyg import datastructures
from verktyg.http.basic import _dump_date


_cookie_params = {
    b'expires', b'path', b'comment', b'max-age',
    b'secure', b'httponly', b'version',
}
_legal_cookie_chars = (
    string.ascii_letters + string.digits + u"!#$%&'*+-.^_`|~:").encode('ascii')

_cookie_quoting_map = {
    b','[0]: b'\\054',
    b';'[0]: b'\\073',
    b'"'[0]: b'\\"',
    b'\\'[0]: b'\\\\',
}
for _i in chain(range(32), range(127, 256)):
    _cookie_quoting_map[_i] = (
        '\\%03o' % _i
    ).encode('latin1')

_octal_re = re.compile(b'\\\\[0-3][0-7][0-7]')
_quote_re = re.compile(b'[\\\\].')
_cookie_re = re.compile(b"""(?x)
    (?P<key>[^=]+)
    \s*=\s*
    (?P<val>
        "(?:[^\\\\"]|\\\\.)*" |
         (?:.*?)
    )
    \s*;
""")


def _cookie_quote(b):
    buf = bytearray()
    all_legal = True

    for char in b:
        if char not in _legal_cookie_chars:
            all_legal = False
            buf.extend(_cookie_quoting_map.get(char, [char]))
        else:
            buf.append(char)

    if all_legal:
        return bytes(buf)
    return bytes(b'"' + buf + b'"')


def _cookie_unquote(b):
    if len(b) < 2:
        return b
    if b[:1] != b'"' or b[-1:] != b'"':
        return b

    b = b[1:-1]

    i = 0
    n = len(b)
    rv = bytearray()
    _push = rv.extend

    while 0 <= i < n:
        o_match = _octal_re.search(b, i)
        q_match = _quote_re.search(b, i)
        if not o_match and not q_match:
            rv.extend(b[i:])
            break
        j = k = -1
        if o_match:
            j = o_match.start(0)
        if q_match:
            k = q_match.start(0)
        if q_match and (not o_match or k < j):
            _push(b[i:k])
            _push(b[k + 1:k + 2])
            i = k + 2
        else:
            _push(b[i:j])
            rv.append(int(b[j + 1:j + 4], 8))
            i = j + 4

    return bytes(rv)


def _make_cookie_domain(domain):
    if domain is None:
        return None
    domain = _encode_idna(domain)
    if b':' in domain:
        domain = domain.split(b':', 1)[0]
    if b'.' in domain:
        return domain
    raise ValueError(
        'Setting \'domain\' for a cookie on a server running locally (ex: '
        'localhost) is not supported by complying browsers. You should '
        'have something like: \'127.0.0.1 localhost dev.localhost\' on '
        'your hosts file and then point your server to run on '
        '\'dev.localhost\' and also set \'domain\' for \'dev.localhost\''
    )


def _cookie_parse_impl(b):
    """Lowlevel cookie parsing facility that operates on bytes."""
    i = 0
    n = len(b)

    while i < n:
        match = _cookie_re.search(b + b';', i)
        if not match:
            break

        key = match.group('key').strip()
        value = match.group('val')
        i = match.end(0)

        # Ignore parameters.  We have no interest in them.
        if key.lower() not in _cookie_params:
            yield _cookie_unquote(key), _cookie_unquote(value)


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
            key = key.decode(charset)
            val = val.decode(charset)
            yield key, val

    return cls(_parse_pairs())


def dump_cookie(key, value='', max_age=None, expires=None, path='/',
                domain=None, secure=False, httponly=False,
                charset='utf-8', sync_expires=True):
    """Creates a new Set-Cookie header without the ``Set-Cookie`` prefix
    The parameters are the same as in the cookie Morsel object in the
    Python standard library but it accepts unicode data, too.

    The return value of this function will be a unicode string tunneled through
    latin1 as required by PEP 3333.

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
    key = key.encode(charset)
    value = value.encode(charset)

    if path is not None:
        path = iri_to_uri(path)
    domain = _make_cookie_domain(domain)
    if isinstance(max_age, timedelta):
        max_age = (max_age.days * 60 * 60 * 24) + max_age.seconds
    if expires is not None:
        if not isinstance(expires, str):
            expires = cookie_date(expires)
    elif max_age is not None and sync_expires:
        expires = cookie_date(time() + max_age).encode('ascii')

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
            v = str(v).encode(charset)
        if q:
            v = _cookie_quote(v)
        tmp += b'=' + v
        buf.append(bytes(tmp))

    # The return value will be an incorrectly encoded latin1 header on
    # for consistency with the headers object
    rv = b'; '.join(buf)
    rv = rv.decode('latin1')
    return rv
