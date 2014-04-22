"""
    werkzeug_dispatch.accept
    ~~~~~~~~~~~~~~~~~~~~~~~~
    Code for selecting handlers based on accept headers

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug import parse_accept_header
from werkzeug.exceptions import NotAcceptable


def select_representation(
        representations,
        accept='*/*', accept_language=None, accept_charset=None):
    max_quality = tuple()
    best = None
    for representation in representations:
        try:
            quality = representation.quality(accept=accept,
                                             accept_language=accept_language,
                                             accept_charset=accept_charset)
        except NotAcceptable:
            continue

        if not isinstance(quality, tuple):
            quality = (quality,)

        # Later bindings take precedence
        if quality >= max_quality:
            best = representation
            max_quality = quality

    if best is None:
        raise NotAcceptable()

    return best.action


class Representation(object):
    def __init__(self, content_type=None, language=None,
                 charset=None, qs=None):
        self.content_type = content_type
        self.language = language
        self.charset = charset

        if qs is None:
            if content_type is None:
                self.qs = 0.001
            else:
                self.qs = 1.0

    def quality(self, *, accept=None, accept_charset=None,
                accept_language=None):
        """
        :param accept: string in the same format as an http `Accept` header

        :param accept_language: string in the same format as an http
            `Accept-Language` header

        :param accept_charset: string in the same format as an http
            `Accept-Charset` header

        :return: a number or tuple of numbers representing the quality of
            the match. By convention tuples should be in content type,
            language, charset order.  Raises `NotAcceptable If the binding does
            not match the request.

        """
        accept = parse_accept_header(accept)

        if self.content_type is None:
            return self.qs

        quality = self.qs * accept.quality(self.content_type)
        if not quality:
            raise NotAcceptable()

        return quality
