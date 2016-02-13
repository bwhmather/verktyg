"""
    verktyg.accept.content_type
    ~~~~~~~~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
import re

from verktyg.exceptions import NotAcceptable
from verktyg.accept import _base


_token_re_str = r'''
    (?:
        [a-zA-Z0-9]+
        (?:
            - [a-zA-Z0-9]+
        )*
    )
'''

# TODO
_value_re = re.compile(
    r'''
        ^
        {token} | \*
        $
    '''.format(token=_token_re_str), re.VERBOSE
)

# TODO
_content_type_value_re = re.compile(
    r'''
        ^
        (?: {token} | \*)
        /
        (?:
            (?:
                (?:{token} \.)?
                {token}
                (?: \+ {token})?
            ) | \*
        )
    '''.format(token=_token_re_str), re.VERBOSE
)


class _ContentTypeRange(_base.Range):
    def _validate_value(self, value):
        if _content_type_value_re.match(value) is None:
            raise ValueError("Invalid value: %r" % value)

    @property
    def type(self):
        type, _ = self.value.split('/')
        return type

    @property
    def subtype(self):
        _, subtype = self.value.split('/')
        return subtype


class ContentTypeAccept(_base.Accept):
    range_type = _ContentTypeRange


class ContentTypeAcceptability(_base.Acceptability):
    def __init__(
                self, content_type, *,
                type_matches, subtype_matches,
                q, qs=None
            ):
        super(ContentTypeAcceptability, self).__init__(
            content_type, match_quality=(
                type_matches, subtype_matches
            ),
            q=q, qs=qs
        )

    @property
    def content_type(self):
        return self._value

    @property
    def type_matches(self):
        return self._match_quality[0]

    @property
    def subtype_matches(self):
        return self._match_quality[1]

    @property
    def exact_match(self):
        return self._match_quality[0] and self._match_quality[1]


class ContentType(_base.Value):
    match_type = ContentTypeAcceptability

    @property
    def type(self):
        type, _ = self.value.split('/')
        return type

    @property
    def subtype(self):
        _, subtype = self.value.split('/')
        return subtype

    def _acceptability_for_option(self, option):
        if option.type == self.type:
            type_matches = True
        elif option.type == '*':
            type_matches = False
        else:
            raise NotAcceptable()

        if option.subtype == self.subtype:
            subtype_matches = True
        elif option.subtype == '*':
            subtype_matches = False
        else:
            raise NotAcceptable()

        return self.match_type(
            self, type_matches=type_matches, subtype_matches=subtype_matches,
            qs=self.qs, q=option.q
        )

    def to_header(self):
        """Returns a string suitable for use as a `Content-Type` header.
        """
        return "%s/%s" % (self.type, self.subtype)


def parse_accept_header(string):
    """Creates a new `ContentTypeAccept` object from an `Accept` header string.
    """
    return ContentTypeAccept(_base.split_accept_string(string))


def parse_content_type_header(string, qs=None):
    """Creates a new `ContentType` object from a mime type string.
    """
    return ContentType(string, qs=qs)
