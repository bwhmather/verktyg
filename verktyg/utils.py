"""
    verktyg.utils
    ~~~~~~~~~~~~~

    This module implements various utilities for WSGI applications.  Most of
    them are used by the request and response wrappers but especially for
    middleware development it makes sense to use them without the wrappers.

    :copyright:
        (c) 2015 Ben Mather, based on Werkzeug, see AUTHORS for more details.
    :license:
        BSD, see LICENSE for more details.
"""
import re
import os

from html import escape

from werkzeug._internal import _DictAccessorProperty, _missing


_filename_ascii_strip_re = re.compile(r'[^A-Za-z0-9_.-]')
_windows_device_files = {
    'CON', 'AUX', 'COM1', 'COM2', 'COM3', 'COM4',
    'LPT1', 'LPT2', 'LPT3', 'PRN', 'NUL',
}


class cached_property(property):
    """A decorator that converts a function into a lazy property.  The
    function wrapped is called the first time to retrieve the result
    and then that calculated result is used the next time you access
    the value::

        class Foo(object):

            @cached_property
            def foo(self):
                # calculate something important here
                return 42

    The class has to have a `__dict__` in order for this property to
    work.
    """
    # implementation detail: A subclass of python's builtin property
    # decorator, we override __get__ to check for a cached value. If one
    # choses to invoke __get__ by hand the property will still work as
    # expected because the lookup logic is replicated in __get__ for
    # manual invocation.

    def __init__(self, func, name=None, doc=None):
        self.__name__ = name or func.__name__
        self.__module__ = func.__module__
        self.__doc__ = doc or func.__doc__
        self.func = func

    def __set__(self, obj, value):
        obj.__dict__[self.__name__] = value

    def __get__(self, obj, type=None):
        if obj is None:
            return self
        value = obj.__dict__.get(self.__name__, _missing)
        if value is _missing:
            value = self.func(obj)
            obj.__dict__[self.__name__] = value
        return value


class header_property(_DictAccessorProperty):
    """Like `environ_property` but for headers."""

    def lookup(self, obj):
        return obj.headers


def get_content_type(mimetype, charset):
    """Returns the full content type string with charset for a mimetype.

    If the mimetype represents text the charset will be appended as charset
    parameter, otherwise the mimetype is returned unchanged.

    :param mimetype:
        The mimetype to be used as content type.
    :param charset:
        The charset to be appended in case it was a text mimetype.
    :return:
        The content type.
    """
    if (
        mimetype.startswith('text/') or
        mimetype == 'application/xml' or
        (mimetype.startswith('application/') and mimetype.endswith('+xml'))
    ):
        mimetype += '; charset=' + charset
    return mimetype


def secure_filename(filename):
    """Pass it a filename and it will return a secure version of it.  This
    filename can then safely be stored on a regular file system and passed
    to :func:`os.path.join`.  The filename returned is an ASCII only string
    for maximum portability.

    On windows systems the function also makes sure that the file is not
    named after one of the special device files.

    >>> secure_filename("My cool movie.mov")
    'My_cool_movie.mov'
    >>> secure_filename("../../../etc/passwd")
    'etc_passwd'
    >>> secure_filename(u'i contain cool \\xfcml\\xe4uts.txt')
    'i_contain_cool_umlauts.txt'

    The function might return an empty filename.  It's your responsibility
    to ensure that the filename is unique and that you generate random
    filename if the function returned an empty one.

    :param filename:
        The filename to secure
    """
    if isinstance(filename, str):
        from unicodedata import normalize
        filename = normalize('NFKD', filename).encode('ascii', 'ignore')
        filename = filename.decode('ascii')
    for sep in os.path.sep, os.path.altsep:
        if sep:
            filename = filename.replace(sep, ' ')
    filename = str(_filename_ascii_strip_re.sub('', '_'.join(
                   filename.split()))).strip('._')

    # on nt a couple of special files are present in each folder.  We
    # have to ensure that the target file is not such a filename.  In
    # this case we prepend an underline
    if (
        os.name == 'nt' and filename and
        filename.split('.')[0].upper() in _windows_device_files
    ):
        filename = '_' + filename

    return filename


def redirect(location, code=302, Response=None):
    """Returns a response object (a WSGI application) that, if called,
    redirects the client to the target location.  Supported codes are 301,
    302, 303, 305, and 307.  300 is not supported because it's not a real
    redirect and 304 because it's the answer for a request with a request
    with defined If-Modified-Since headers.

    :param location:
        The location the response should redirect to.
    :param code:
        The redirect status code. defaults to 302.
    :param class Response:
        A Response class to use when instantiating a response. The default is
        :class:`verktyg.responses.Response` if unspecified.
    """
    if Response is None:
        from verktyg.responses import Response

    display_location = escape(location)
    if isinstance(location, str):
        # Safe conversion is necessary here as we might redirect
        # to a broken URI scheme (for instance itms-services).
        from verktyg.urls import iri_to_uri
        location = iri_to_uri(location)
    response = Response(
        '<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">\n'
        '<title>Redirecting...</title>\n'
        '<h1>Redirecting...</h1>\n'
        '<p>You should be redirected automatically to target URL: '
        '<a href="%s">%s</a>.  If not click the link.' %
        (escape(location), display_location),
        code, mimetype='text/html'
    )
    response.headers['Location'] = location
    return response


def append_slash_redirect(environ, code=301):
    """Redirects to the same URL but with a slash appended.  The behavior
    of this function is undefined if the path ends with a slash already.

    :param environ:
        The WSGI environment for the request that triggers the redirect.
    :param code:
        The status code for the redirect.
    """
    new_path = environ['PATH_INFO'].strip('/') + '/'
    query_string = environ.get('QUERY_STRING')
    if query_string:
        new_path += '?' + query_string
    return redirect(new_path, code)
