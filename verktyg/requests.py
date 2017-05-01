"""
    verktyg.request
    ~~~~~~~~~~~~~~~

    The wrappers are simple request and response objects which you can
    subclass to do whatever you want them to do.  The request object contains
    the information transmitted by the client (webbrowser) and the response
    object contains all the information sent back to the browser.

    An important detail is that the request object is created with the WSGI
    environ and will act as high-level proxy whereas the response object is an
    actual WSGI application.

    Like everything else in Werkzeug these objects will work correctly with
    unicode data.  Incoming form data parsed by the response object will be
    decoded into an unicode object if possible and if it makes sense.


    :copyright: (c) 2014 by the Werkzeug Team, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
from io import BytesIO
from urllib.parse import parse_qsl

from verktyg.utils import cached_property
from verktyg.datastructures import (
    ImmutableMultiDict,
    ImmutableTypeConversionDict,
    ImmutableList,
    iter_multi_items,
)
from verktyg.http import (
    parse_cache_control_header, parse_etags,
    parse_date, parse_set_header, parse_authorization_header,
    parse_options_header, parse_if_range_header, parse_cookie,
    parse_range_header,
    RequestCacheControl,
)
from verktyg.wsgi import (
    EnvironHeaders, wsgi_decoding_dance,
    get_current_url, get_host, get_input_stream, get_content_length
)


def _assert_not_shallow(request):
    if request.shallow:
        raise RuntimeError(
            'A shallow request tried to consume form data.  If you really '
            'want to do that, set `shallow` to False.'
        )


class BaseRequest(object):

    """Very basic request object.  This does not implement advanced stuff like
    entity tag parsing or cache controls.  The request object is created with
    the WSGI environment as first argument and will add itself to the WSGI
    environment as ``'verktyg.request'`` unless it's created with
    `populate_request` set to False.

    There are a couple of mixins available that add additional functionality
    to the request object, there is also a class called `Request` which
    subclasses `BaseRequest` and all the important mixins.

    It's a good idea to create a custom subclass of the :class:`BaseRequest`
    and add missing functionality either via mixins or direct implementation.
    Here an example for such subclasses::

        from verktyg.wrappers import BaseRequest, ETagRequestMixin

        class Request(BaseRequest, ETagRequestMixin):
            pass

    Request objects are **read only**.  As of 0.5 modifications are not
    allowed in any place.  Unlike the lower level parsing functions the
    request object will use immutable objects everywhere possible.

    Per default the request object will assume all the text data is `utf-8`
    encoded.  Please refer to `the unicode chapter <unicode.txt>`_ for more
    details about customizing the behavior.

    Per default the request object will be added to the WSGI
    environment as `verktyg.request` to support the debugging system.
    If you don't want that, set `populate_request` to `False`.

    If `shallow` is `True` the environment is initialized as shallow
    object around the environ.  Every operation that would modify the
    environ in any way (such as consuming form data) raises an exception
    unless the `shallow` attribute is explicitly set to `False`.  This
    is useful for middlewares where you don't want to consume the form
    data by accident.  A shallow request is not populated to the WSGI
    environment.
    """
    #: the error handling procedure for errors, defaults to 'replace'
    encoding_errors = 'replace'

    #: the maximum content length.  This is forwarded to the form data
    #: parsing function (:func:`parse_form_data`).  When set and the
    #: :attr:`form` or :attr:`files` attribute is accessed and the
    #: parsing fails because more than the specified value is transmitted
    #: a :exc:`~verktyg.exceptions.RequestEntityTooLarge` exception is raised.
    #:
    #: Have a look at :ref:`dealing-with-request-data` for more details.
    max_content_length = None

    #: the maximum form field size.  This is forwarded to the form data
    #: parsing function (:func:`parse_form_data`).  When set and the
    #: :attr:`form` or :attr:`files` attribute is accessed and the
    #: data in memory for post data is longer than the specified value a
    #: :exc:`~verktyg.exceptions.RequestEntityTooLarge` exception is raised.
    #:
    #: Have a look at :ref:`dealing-with-request-data` for more details.
    max_form_memory_size = None

    #: the class to use for `args` and `form`.  The default is an
    #: :class:`~verktyg.datastructures.ImmutableMultiDict` which supports
    #: multiple values per key.  alternatively it makes sense to use an
    #: :class:`~verktyg.datastructures.ImmutableOrderedMultiDict` which
    #: preserves order or a :class:`~verktyg.datastructures.ImmutableDict`
    #: which is the fastest but only remembers the last key.  It is also
    #: possible to use mutable structures, but this is not recommended.
    parameter_storage_class = ImmutableMultiDict

    #: the type to be used for list values from the incoming WSGI environment.
    #: By default an :class:`~verktyg.datastructures.ImmutableList` is used
    #: (for example for :attr:`access_list`).
    list_storage_class = ImmutableList

    #: the type to be used for dict values from the incoming WSGI environment.
    #: By default an
    #: :class:`~verktyg.datastructures.ImmutableTypeConversionDict` is used
    #: (for example for :attr:`cookies`).
    dict_storage_class = ImmutableTypeConversionDict

    #: Optionally a list of hosts that is trusted by this request.  By default
    #: all hosts are trusted which means that whatever the client sends the
    #: host is will be accepted.
    #:
    #: This is the recommended setup as a webserver should manually be set up
    #: to only route correct hosts to the application, and remove the
    #: `X-Forwarded-Host` header if it is not being used (see
    #: :func:`verktyg.wsgi.get_host`).
    trusted_hosts = None

    #: Indicates whether the data descriptor should be allowed to read and
    #: buffer up the input stream.  By default it's enabled.
    disable_data_descriptor = False

    def __init__(self, environ, populate_request=True, shallow=False):
        self.environ = environ
        if populate_request and not shallow:
            self.environ['verktyg.request'] = self
        self.shallow = shallow
        self._on_close = []
        super(BaseRequest, self).__init__()

    def __repr__(self):
        # make sure the __repr__ even works if the request was created
        # from an invalid WSGI environment.  If we display the request
        # in a debug session we don't want the repr to blow up.
        args = []
        try:
            args.append("'%s'" % self.url)
            args.append('[%s]' % self.method)
        except Exception:
            args.append('(invalid WSGI environ)')

        return '<%s %s>' % (
            self.__class__.__name__,
            ' '.join(args)
        )

    @property
    def app(self):
        """The verktyg application the created the request

        :return: a `verktyg.application.Application` object or `None`
        """
        return self.environ.get('verktyg.application')

    @classmethod
    def from_values(cls, *args, **kwargs):
        """Create a new request object based on the values provided.  If
        environ is given missing values are filled from there.  This method is
        useful for small scripts when you need to simulate a request from an
        URL.
        Do not use this method for unittesting, there is a full featured client
        object (:class:`Client`) that allows to create multipart requests,
        support for cookies etc.

        This accepts the same options as the
        :class:`~verktyg.test.EnvironBuilder`.
        :return: request object
        """
        from verktyg.test import EnvironBuilder
        builder = EnvironBuilder(*args, **kwargs)
        try:
            return builder.get_request(cls)
        finally:
            builder.close()

    def _get_stream_for_parsing(self):
        """This is the same as accessing :attr:`stream` with the difference
        that if it finds cached data from calling :meth:`get_data` first it
        will create a new stream out of the cached data.
        """
        cached_data = getattr(self, '_cached_data', None)
        if cached_data is not None:
            return BytesIO(cached_data)
        return self.stream

    def call_on_close(self, func):
        """Adds a function to the internal list of functions that should
        be called as part of closing down the request.  Also returns the
        function that was passed so that this can be used as a decorator.
        """
        self._on_close.append(func)
        return func

    def close(self):
        """Closes associated resources of this request object.  This
        closes all file handles explicitly.  You can also use the request
        object in a with statement which will automatically close it.
        """
        files = self.__dict__.get('files')
        for key, value in iter_multi_items(files or ()):
            value.close()
        for func in self._on_close:
            func()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, tb):
        self.close()

    @cached_property
    def stream(self):
        """The stream to read incoming data from.  Unlike :attr:`input_stream`
        this stream is properly guarded that you can't accidentally read past
        the length of the input.  Werkzeug will internally always refer to
        this stream to read data which makes it possible to wrap this
        object with a stream that does filtering.
        """
        _assert_not_shallow(self)
        return get_input_stream(self.environ)

    @cached_property
    def input_stream(self):
        """The WSGI input stream.

        In general it's a bad idea to use this one because you can easily read
        past the boundary.  Use the :attr:`stream` instead.
        """
        return self.environ.get('wsgi.input')

    @cached_property
    def args(self):
        """The parsed URL parameters.  By default an
        :class:`~verktyg.datastructures.ImmutableMultiDict`
        is returned from this function.  This can be changed by setting
        :attr:`parameter_storage_class` to a different type.  This might
        be necessary if the order of the form data is important.
        """
        qs = wsgi_decoding_dance(
            self.environ.get('QUERY_STRING', ''),
            errors=self.encoding_errors,
        )
        return self.parameter_storage_class(parse_qsl(
            qs, errors=self.encoding_errors,
        ))

    def get_data(self, cache=True, as_text=False):
        """This reads the buffered incoming data from the client into one
        bytestring.  By default this is cached but that behavior can be
        changed by setting `cache` to `False`.

        Usually it's a bad idea to call this method without checking the
        content length first as a client could send dozens of megabytes or more
        to cause memory problems on the server.

        If `as_text` is set to `True` the return value will be a decoded
        unicode string.
        """
        rv = getattr(self, '_cached_data', None)
        if rv is None:
            rv = self.stream.read()
            if cache:
                self._cached_data = rv
        if as_text:
            # TODO charset
            rv = rv.decode('utf-8', self.encoding_errors)
        return rv

    @cached_property
    def cookies(self):
        """Read only access to the retrieved cookie values as dictionary."""
        return parse_cookie(
            self.environ, errors=self.encoding_errors,
            cls=self.dict_storage_class
        )

    @cached_property
    def headers(self):
        """The headers from the WSGI environ as immutable
        :class:`~verktyg.wsgi.EnvironHeaders`.
        """
        return EnvironHeaders(self.environ)

    @cached_property
    def path(self):
        """Requested path as unicode.  This works a bit like the regular path
        info in the WSGI environment but will always include a leading slash,
        even if the URL root is accessed.
        """
        raw_path = wsgi_decoding_dance(
            self.environ.get('PATH_INFO') or '', errors=self.encoding_errors
        )
        return '/' + raw_path.lstrip('/')

    @cached_property
    def full_path(self):
        """Requested path as unicode, including the query string."""
        return self.path + u'?' + self.query_string

    @cached_property
    def script_root(self):
        """The root path of the script without the trailing slash."""
        raw_path = wsgi_decoding_dance(
            self.environ.get('SCRIPT_NAME') or '',
            errors=self.encoding_errors
        )
        return raw_path.rstrip('/')

    @cached_property
    def url(self):
        """The reconstructed current URL as IRI.
        See also: :attr:`trusted_hosts`.
        """
        return get_current_url(
            self.environ, trusted_hosts=self.trusted_hosts,
        )

    @cached_property
    def base_url(self):
        """Like :attr:`url` but without the querystring
        See also: :attr:`trusted_hosts`.
        """
        return get_current_url(
            self.environ, strip_querystring=True,
            trusted_hosts=self.trusted_hosts,
        )

    @cached_property
    def url_root(self):
        """The full URL root (with hostname), this is the application
        root as IRI.
        See also: :attr:`trusted_hosts`.
        """
        return get_current_url(
            self.environ, True, trusted_hosts=self.trusted_hosts,
        )

    @cached_property
    def host_url(self):
        """Just the host with scheme as IRI.
        See also: :attr:`trusted_hosts`.
        """
        return get_current_url(
            self.environ, host_only=True, trusted_hosts=self.trusted_hosts,
        )

    @cached_property
    def host(self):
        """Just the host including the port if available.
        See also: :attr:`trusted_hosts`.
        """
        return get_host(self.environ, trusted_hosts=self.trusted_hosts)

    @cached_property
    def query_string(self):
        return wsgi_decoding_dance(
            self.environ.get('QUERY_STRING') or '', errors=self.encoding_errors
        )

    @cached_property
    def method(self):
        """The transmission method. (For example ``'GET'`` or ``'POST'``).
        """
        return self.environ.get('REQUEST_METHOD', 'GET').upper()

    @cached_property
    def access_route(self):
        """If a forwarded header exists this is a list of all ip addresses
        from the client ip to the last proxy server.
        """
        if 'HTTP_X_FORWARDED_FOR' in self.environ:
            addr = self.environ['HTTP_X_FORWARDED_FOR'].split(',')
            return self.list_storage_class([x.strip() for x in addr])
        elif 'REMOTE_ADDR' in self.environ:
            return self.list_storage_class([self.environ['REMOTE_ADDR']])
        return self.list_storage_class()

    @property
    def remote_addr(self):
        """The remote address of the client."""
        return self.environ.get('REMOTE_ADDR')

    @cached_property
    def remote_user(self):
        """If the server supports user authentication, and the script is
        protected, this attribute contains the username the user has
        authenticated as.
        """
        return self.environ.get('REMOTE_USER')

    @cached_property
    def scheme(self):
        """URL scheme (http or https).
        """
        return self.environ.get('wsgi.url_scheme')

    @property
    def is_xhr(self):
        """True if the request was triggered via a JavaScript XMLHttpRequest.

        This only works with libraries that support the `X-Requested-With`
        header and set it to "XMLHttpRequest".  Libraries that do that are
        prototype, jQuery and Mochikit and probably some more.
        """
        requested_with = self.environ.get('HTTP_X_REQUESTED_WITH', '').lower()
        return requested_with.lower() == 'xmlhttprequest'

    @property
    def is_secure(self):
        """`True` if the request is made over an encrypted connection
        """
        self.environ['wsgi.url_scheme'] == 'https',

    @property
    def is_multithread(self):
        """`True` if the application is served by a multithreaded WSGI server.
        """
        return self.environ.get('wsgi.multithread')

    @property
    def is_multiprocess(self):
        """`True` if the application is served by a multiprocess WSGI server.
        """
        return self.environ.get('wsgi.multiprocess')

    @property
    def is_run_once(self):
        """`True` if the application will be executed only once in a process
        lifetime.

        This is the case for CGI for example, but it's not guaranteed that the
        execution only happens one time.
        """
        return self.environ.get('wsgi.run_once')


class ETagRequestMixin(object):

    """Add entity tag and cache descriptors to a request object or object with
    a WSGI environment available as :attr:`~BaseRequest.environ`.  This not
    only provides access to etags but also to the cache control header.
    """

    @cached_property
    def cache_control(self):
        """A :class:`~verktyg.http.RequestCacheControl` object
        for the incoming cache control headers.
        """
        cache_control = self.environ.get('HTTP_CACHE_CONTROL')
        return parse_cache_control_header(
            cache_control, None, RequestCacheControl,
        )

    @cached_property
    def if_match(self):
        """An object containing all the etags in the `If-Match` header.

        :rtype: :class:`~verktyg.http.ETags`
        """
        return parse_etags(self.environ.get('HTTP_IF_MATCH'))

    @cached_property
    def if_none_match(self):
        """An object containing all the etags in the `If-None-Match` header.

        :rtype: :class:`~verktyg.http.ETags`
        """
        return parse_etags(self.environ.get('HTTP_IF_NONE_MATCH'))

    @cached_property
    def if_modified_since(self):
        """The parsed `If-Modified-Since` header as datetime object."""
        return parse_date(self.environ.get('HTTP_IF_MODIFIED_SINCE'))

    @cached_property
    def if_unmodified_since(self):
        """The parsed `If-Unmodified-Since` header as datetime object."""
        return parse_date(self.environ.get('HTTP_IF_UNMODIFIED_SINCE'))

    @cached_property
    def if_range(self):
        """The parsed `If-Range` header.

        :rtype: :class:`~verktyg.http.IfRange`
        """
        return parse_if_range_header(self.environ.get('HTTP_IF_RANGE'))

    @cached_property
    def range(self):
        """The parsed `Range` header.

        :rtype: :class:`~verktyg.http.Range`
        """
        return parse_range_header(self.environ.get('HTTP_RANGE'))


class AuthorizationMixin(object):

    """Adds an :attr:`authorization` property that represents the parsed
    value of the `Authorization` header as
    :class:`~verktyg.http.Authorization` object.
    """

    @cached_property
    def authorization(self):
        """The `Authorization` object in parsed form."""
        header = self.environ.get('HTTP_AUTHORIZATION')
        return parse_authorization_header(header)


class StreamOnlyMixin(object):

    """If mixed in before the request object this will change the behavior
    of it to disable handling of form parsing.  This disables the
    :attr:`files`, :attr:`form` attributes and will just provide a
    :attr:`stream` attribute that is always available.
    """

    disable_data_descriptor = True
    want_form_data_parsed = False


class CommonRequestDescriptorsMixin(object):

    """A mixin for :class:`BaseRequest` subclasses.  Request objects that
    mix this class in will automatically get descriptors for a couple of
    HTTP headers with automatic type conversion.
    """

    @property
    def content_type(self):
        """The Content-Type entity-header field indicates the media type of
        the entity-body sent to the recipient or, in the case of the HEAD
        method, the media type that would have been sent had the request
        been a GET.
        """
        return self.environ.get('CONTENT_TYPE')

    @cached_property
    def content_length(self):
        """The Content-Length entity-header field indicates the size of the
        entity-body in bytes or, in the case of the HEAD method, the size of
        the entity-body that would have been sent had the request been a
        GET.
        """
        return get_content_length(self.environ)

    @property
    def content_encoding(self):
        """The Content-Encoding entity-header field is used as a modifier to
        the media-type.  When present, its value indicates what additional
        content codings have been applied to the entity-body, and thus what
        decoding mechanisms must be applied in order to obtain the media-type
        referenced by the Content-Type header field.
        """
        return self.environ.get('HTTP_CONTENT_ENCODING')

    @property
    def content_md5(self):
        """The Content-MD5 entity-header field, as defined in RFC 1864, is an
        MD5 digest of the entity-body for the purpose of providing an
        end-to-end message integrity check (MIC) of the entity-body.  (Note:
        a MIC is good for detecting accidental modification of the
        entity-body in transit, but is not proof against malicious attacks.)
        """
        return self.environ.get('HTTP_CONTENT_MD5')

    @property
    def referrer(self):
        """The Referer[sic] request-header field allows the client to specify,
        for the server's benefit, the address (URI) of the resource from which
        the Request-URI was obtained (the "referrer", although the header
        field is misspelled).
        """
        return self.environ.get('HTTP_REFERER')

    @property
    def date(self):
        """The Date general-header field represents the date and time at which
        the message was originated, having the same semantics as orig-date
        in RFC 822.
        """
        return parse_date(self.environ.get('HTTP_DATE'))

    @property
    def max_forwards(self):
        """The Max-Forwards request-header field provides a mechanism with the
        TRACE and OPTIONS methods to limit the number of proxies or gateways
        that can forward the request to the next inbound server.
        """
        try:
            return int(self.environ.get('HTTP_MAX_FORWARDS'))
        except ValueError:
            return None

    def _parse_content_type(self):
        if not hasattr(self, '_parsed_content_type'):
            self._parsed_content_type = parse_options_header(
                self.environ.get('CONTENT_TYPE', '')
            )

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

    @cached_property
    def pragma(self):
        """The Pragma general-header field is used to include
        implementation-specific directives that might apply to any recipient
        along the request/response chain.  All pragma directives specify
        optional behavior from the viewpoint of the protocol; however, some
        systems MAY require that behavior be consistent with the directives.
        """
        return parse_set_header(self.environ.get('HTTP_PRAGMA', ''))


# TODO deprecate.  Superseded by request class building in ApplicationBuilder
class Request(
    BaseRequest,
    ETagRequestMixin,
    AuthorizationMixin,
    CommonRequestDescriptorsMixin,
):

    """Full featured request object implementing the following mixins:

    - :class:`AcceptMixin` for accept header parsing
    - :class:`ETagRequestMixin` for etag and cache control handling
    - :class:`AuthorizationMixin` for http auth handling
    - :class:`CommonRequestDescriptorsMixin` for common headers
    """


class PlainRequest(StreamOnlyMixin, Request):

    """A request object without special form parsing capabilities.
    """
