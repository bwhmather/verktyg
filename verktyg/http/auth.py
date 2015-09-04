"""
    verktyg.http.auth
    ~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import base64

from verktyg import datastructures
from verktyg.http.basic import (
    wsgi_to_bytes, bytes_to_wsgi, parse_dict_header,
    dump_header, quote_header_value, parse_set_header,
)


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
    :class:`~WWWAuthenticate` object.

    :param value:
        A WWW-Authenticate header to parse.
    :param on_update:
        An optional callable that is called every time a value on the
        :class:`~WWWAuthenticate` object is changed.
    :return:
        A:class:`~WWWAuthenticate` object.
    """
    if not value:
        return WWWAuthenticate(on_update=on_update)
    try:
        auth_type, auth_info = value.split(None, 1)
        auth_type = auth_type.lower()
    except (ValueError, AttributeError):
        return WWWAuthenticate(value.strip().lower(), on_update=on_update)
    return WWWAuthenticate(
        auth_type, parse_dict_header(auth_info), on_update
    )
