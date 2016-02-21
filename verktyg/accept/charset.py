"""
    verktyg.accept.charset
    ~~~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
from verktyg.accept import _base


class _CharsetRange(_base.Range):
    def _validate_param(self, key, value):
        raise ValueError("Accept-Charset header does not take parameters")


class CharsetAccept(_base.Accept):
    range_type = _CharsetRange


class CharsetAcceptability(_base.Acceptability):
    def __init__(self, value, *, exact_match, q, qs=None):
        super(CharsetAcceptability, self).__init__(
            value, match_quality=exact_match, q=q, qs=qs
        )

    @property
    def charset(self):
        return self._value

    @property
    def exact_match(self):
        return self._match_quality


class Charset(_base.Value):
    match_type = CharsetAcceptability


def parse_accept_charset_header(string):
    return CharsetAccept(_base.split_accept_string(string))


def parse_charset_header(string):
    return Charset(string)
