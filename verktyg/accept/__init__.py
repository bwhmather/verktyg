"""
    verktyg.accept
    ~~~~~~~~~~~~~~

    Code for selecting handlers based on accept headers

    http://www.w3.org/Protocols/rfc2616/rfc2616-sec14.html

    :copyright: (c) 2015 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
import functools

from verktyg.accept.content_type import (
    parse_content_type_header, parse_accept_header
)
from verktyg.accept.language import (
    parse_language_header, parse_accept_language_header,
)
from verktyg.accept.charset import (
    parse_charset_header, parse_accept_charset_header,
)

from verktyg.exceptions import NotAcceptable


@functools.total_ordering
class Acceptability(object):
    def __init__(
                self, *,
                content_type_acceptability,
                language_acceptability,
                charset_acceptability,
                qs
            ):
        self._content_type_acceptability = content_type_acceptability
        self._language_acceptability = language_acceptability
        self._charset_acceptability = charset_acceptability
        self._qs = qs

    def __eq__(self, other):
        if (other._content_type_acceptability !=
                self._content_type_acceptability):
            return False
        if other._language_acceptability != self._language_acceptability:
            return False
        if other._charset_acceptability != self._charset_acceptability:
            return False
        if other._qs != self._qs:
            return False
        return True

    def __gt__(self, other):
        def _gt(self, other):
            if (self is None) and (other is None):
                return False
            if self <= other:
                return False
            return True

        if _gt(
                self._content_type_acceptability,
                other._content_type_acceptability):
            return True
        if _gt(
                self._language_acceptability,
                other._language_acceptability):
            return True
        if _gt(
                self._charset_acceptability,
                other._charset_acceptability):
            return True
        if _gt(
                self._qs,
                other._qs):
            return True
        return False


def select_representation(
            representations,
            accept='*/*', accept_language='*', accept_charset='*'
        ):
    highest_acceptability = None
    best_representation = None

    if accept is None:
        accept = '*/*'
    if isinstance(accept, str):
        accept = parse_accept_header(accept)

    if accept_language is None:
        accept_language = '*'
    if isinstance(accept_language, str):
        accept_language = parse_accept_language_header(accept_language)

    if accept_charset is None:
        accept_charset = '*'
    if isinstance(accept_charset, str):
        accept_charset = parse_accept_charset_header(accept_charset)

    for representation in representations:
        try:
            acceptability = representation.acceptability(
                accept=accept,
                accept_language=accept_language,
                accept_charset=accept_charset
            )
        except NotAcceptable:
            continue

        if (highest_acceptability is None or
                acceptability >= highest_acceptability):
            highest_acceptability = acceptability
            best_representation = representation

    if best_representation is None:
        raise NotAcceptable()

    return best_representation


class Representation(object):
    def __init__(self, *, content_type=None, language=None,
                 charset=None, qs=None):
        if isinstance(content_type, str):
            content_type = parse_content_type_header(content_type)
        self._content_type = content_type

        if isinstance(language, str):
            language = parse_language_header(language)
        self._language = language

        if isinstance(charset, str):
            charset = parse_charset_header(charset)
        self._charset = charset

        if qs is None:
            qs = 1.0
        self._qs = max(min(float(qs), 1.0), 0.0)

    def acceptability(
                self, *,
                accept=None,
                accept_charset=None,
                accept_language=None
            ):
        """
        :param accept:
            String in the same format as an http `Accept` header

        :param accept_language:
            String in the same format as an http `Accept-Language` header

        :param accept_charset:
            String in the same format as an http `Accept-Charset` header

        :return:
            An orderable `Acceptability` object representing the quality of the
            match.

        :raises NotAcceptable: If the binding does not match the request.
        """
        content_type_acceptability = (
            self._content_type.acceptability(accept)
            if self._content_type is not None else
            None
        )

        language_acceptability = (
            self._content_type.acceptability(accept)
            if self._language is not None else
            None
        )

        charset_acceptability = (
            self._charset.acceptability
            if self._charset is not None else
            None
        )

        return Acceptability(
            content_type_acceptability=content_type_acceptability,
            language_acceptability=language_acceptability,
            charset_acceptability=charset_acceptability,
            qs=self._qs,
        )

    def __repr__(self):
        output = "<%s" % self.__class__.__name__
        if self._content_type is not None:
            output += " content_type=%r" % self._content_type
        if self._language is not None:
            output += " language=%r" % self._language
        if self._charset is not None:
            output += " charset=%r" % self._charset
        output += ">"
        return output
