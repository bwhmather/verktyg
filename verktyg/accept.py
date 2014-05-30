# -*- coding: utf-8 -*-
"""
    verktyg.accept
    ~~~~~~~~~~~~~~

    Code for selecting handlers based on accept headers

    http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import mimeparse

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

    return best


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

    def quality(self, accept=None, accept_charset=None,
                accept_language=None):
        """
        :param accept: string in the same format as an http `Accept` header

        :param accept_language: string in the same format as an http
            `Accept-Language` header

        :param accept_charset: string in the same format as an http
            `Accept-Charset` header

        :return: a number or tuple of tuples representing the quality of
            the match. By convention outer tuples should be in content type,
            language, charset order.  Raises `NotAcceptable If the binding does
            not match the request.

        """
        if self.content_type is None:
            # TODO
            return 5, self.qs

        if accept is None:
            return 0, self.qs

        accept = [
            mimeparse.parse_media_range(media_range)
            for media_range in accept.split(',')
        ]

        fitness, quality = mimeparse.fitness_and_quality_parsed(
            self.content_type, accept
        )

        if fitness == -1:
            raise NotAcceptable()

        return fitness, quality * self.qs
