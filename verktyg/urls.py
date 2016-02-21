"""
    werkzeug.urls
    ~~~~~~~~~~~~~

    :copyright:
        (c) 2016 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
from urllib.parse import (
    urlsplit, urlunsplit,
    quote as urlquote, quote_plus as urlquote_plus,
)

from werkzeug._internal import _encode_idna, _decode_idna


_hexdigits = '0123456789ABCDEFabcdef'
_hextobyte = dict(
    ((a + b).encode(), int(a + b, 16))
    for a in _hexdigits for b in _hexdigits
)


def _safe_urlunquote_to_bytes(string, unsafe=''):
    if isinstance(string, str):
        string = string.encode('utf-8')
    if isinstance(unsafe, str):
        unsafe = unsafe.encode('utf-8')
    unsafe = frozenset(bytearray(unsafe))
    bits = iter(string.split(b'%'))
    result = bytearray(next(bits, b''))
    for item in bits:
        try:
            char = _hextobyte[item[:2]]
            if char in unsafe:
                raise KeyError()
            result.append(char)
            result.extend(item[2:])
        except KeyError:
            result.extend(b'%')
            result.extend(item)
    return bytes(result)


def _safe_urlunquote(string, charset='utf-8', errors='replace', unsafe=''):
    """URL decode a single string with a given encoding.  If the charset
    is set to `None` no unicode decoding is performed and raw bytes
    are returned.

    :param s:
        The string to unquote.
    :param charset:
        The charset of the query string.  If set to `None` no unicode decoding
        will take place.
    :param errors:
        The error handling for the charset decoding.
    """
    rv = _safe_urlunquote_to_bytes(string, unsafe)
    if charset is not None:
        rv = rv.decode(charset, errors)
    return rv


def uri_to_iri(uri, errors='replace'):
    r"""Converts a URI in a given charset to a IRI.

    Examples for URI versus IRI:

    >>> uri_to_iri(b'http://xn--n3h.net/')
    u'http://\u2603.net/'
    >>> uri_to_iri(b'http://%C3%BCser:p%C3%A4ssword@xn--n3h.net/p%C3%A5th')
    u'http://\xfcser:p\xe4ssword@\u2603.net/p\xe5th'

    Query strings are left unchanged:

    >>> uri_to_iri('/?foo=24&x=%26%2f')
    u'/?foo=24&x=%26%2f'

    :param uri:
        The URI to convert.
    :param charset:
        The charset of the URI.
    :param errors:
        The error handling on decode.
    """
    assert isinstance(uri, str)
    uri = urlsplit(uri)

    host = _decode_idna(uri.hostname) if uri.hostname else ''
    if ':' in host:
        host = '[%s]' % host

    netloc = host

    if uri.port:
        if not 0 <= int(uri.port) <= 65535:
            raise ValueError('Invalid port')
        netloc = '%s:%s' % (netloc, uri.port)

    if uri.username or uri.password:
        if uri.username:
            username = _safe_urlunquote(
                uri.username, errors='strict', unsafe='/:%'
            )
        else:
            username = ''

        if uri.password:
            password = _safe_urlunquote(
                uri.password, errors='strict', unsafe='/:%'
            )
            auth = '%s:%s' % (username, password)
        else:
            auth = username

        netloc = '%s@%s' % (auth, netloc)

    path = _safe_urlunquote(
        uri.path, errors=errors, unsafe='%/;?'
    )
    query = _safe_urlunquote(
        uri.query, errors=errors, unsafe='%;/?:@&=+,$#'
    )
    fragment = _safe_urlunquote(
        uri.fragment, errors=errors, unsafe='%;/?:@&=+,$#'
    )
    return urlunsplit(
        (uri.scheme, netloc, path, query, fragment)
    )


def _encode_netloc(components):
    host = ''
    if components.hostname:
        host = _encode_idna(components.hostname).decode('ascii')
    if ':' in host:
        host = '[%s]' % host

    netloc = host

    if components.port:
        if not 0 <= int(components.port) <= 65535:
            raise ValueError('Invalid port')
        netloc = '%s:%s' % (netloc, components.port)

    if components.username or components.password:
        if components.username:
            username = urlquote(
                components.username, safe='/:%'
            )
        else:
            username = ''

        if components.password:
            password = urlquote(
                components.password, safe='/:%'
            )
            auth = '%s:%s' % (username, password)
        else:
            auth = username

        netloc = '%s@%s' % (auth, netloc)
    return netloc


def iri_to_uri(iri):
    r"""Converts any unicode based IRI to an acceptable ASCII URI. Verktyg
    always uses utf-8 URLs internally because this is what browsers and HTTP do
    as well. In some places where it accepts an URL it also accepts a unicode
    IRI and converts it into a URI.

    Examples for IRI versus URI:

    >>> iri_to_uri(u'http://☃.net/')
    'http://xn--n3h.net/'
    >>> iri_to_uri(u'http://üser:pässword@☃.net/påth')
    'http://%C3%BCser:p%C3%A4ssword@xn--n3h.net/p%C3%A5th'

    :param iri:
        The IRI to convert.

    :returns:
        The equivalent URI as an ascii only string object.
    """
    assert isinstance(iri, str)

    iri = urlsplit(iri)

    netloc = _encode_netloc(iri)

    path = urlquote(
        iri.path, safe='/:~+%'
    )
    query = urlquote(
        iri.query, safe='%&[]:;$*()+,!?*/='
    )
    fragment = urlquote(
        iri.fragment, safe='=%&[]:;$()+,!?*/'
    )

    return urlunsplit(
        (iri.scheme, netloc, path, query, fragment)
    )


def url_fix(s, charset='utf-8'):
    r"""Sometimes you get an URL by a user that just isn't a real URL because
    it contains unsafe characters like ' ' and so on. This function can fix
    some of the problems in a similar way browsers handle data entered by the
    user:

    >>> url_fix(u'http://de.wikipedia.org/wiki/Elf (Begriffskl\xe4rung)')
    'http://de.wikipedia.org/wiki/Elf%20(Begriffskl%C3%A4rung)'

    :param s:
        The string with the URL to fix.
    :param charset:
        The target charset for the URL if the url was given as unicode string.
    """
    # First step is to convert backslashes (which are invalid in URLs anyways)
    # to slashes.  This is consistent with what Chrome does.
    s = s.replace('\\', '/')

    # For the specific case that we look like a malformed windows URL
    # we want to fix this up manually:
    if (
        s.startswith('file://') and
        s[7:8].isalpha() and
        s[8:10] in (':/', '|/')
    ):
        s = 'file:///' + s[7:]

    url = urlsplit(s)

    netloc = _encode_netloc(url)

    path = urlquote(
        url.path, encoding=charset, safe='/%+$!*\'(),'
    )
    qs = urlquote_plus(
        url.query, encoding=charset, safe=':&%=+$!*\'(),'
    )
    anchor = urlquote_plus(
        url.fragment, encoding=charset, safe=':&%=+$!*\'(),'
    )

    return urlunsplit(
        (url.scheme, netloc, path, qs, anchor)
    )
