"""
    verktyg.http.accept
    ~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2015 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
import re
import functools

from verktyg.datastructures import ImmutableDict
from verktyg.exceptions import NotAcceptable


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
        ''' + _token_re_str + ''' | \*
        $
    ''', re.VERBOSE
)

# TODO
_content_type_value_re = re.compile(
    r'''
        ^
        (?: ''' + _token_re_str + ''' | \*)
        /
        (?:
            (?:
                (?:''' + _token_re_str + ''' \.)?
                ''' + _token_re_str + '''
                (?: \+ ''' + _token_re_str + ''')?
            ) | \*
        )
    ''', re.VERBOSE
)


# TODO better name
class _Value(object):
    """Base class for a value that the server to be proposed during content
    negotiation.
    """
    match_type = None

    def __init__(self, value, *, qs=None):
        self.value = value
        self.qs = qs

    def _acceptability_for_option(self, option):
        if option.value == '*':
            exact_match = False
        elif self.value == option.value:
            exact_match = True
        else:
            raise NotAcceptable()

        return self.match_type(
            self, exact_match=exact_match,
            q=option.q, qs=self.qs
        )

    def acceptability(self, accept):
        best_match = None

        for option in accept:
            try:
                match = self._acceptability_for_option(option)
            except NotAcceptable:
                pass
            else:
                if best_match is None or match > best_match:
                    best_match = match

        if best_match is None:
            raise NotAcceptable()

        return best_match

    def __str__(self):
        return self.to_header()

    def to_header(self):
        """Returns a string suitable for use in the corresponding header
        """
        return self.value


class _Range(object):
    def __init__(self, value, q=1.0, params=None):
        self._validate_value(value)
        self.value = value

        self.q = max(min(float(q), 1.0), 0.0)

        if params is None:
            params = {}
        for param in params.items():
            self._validate_param(*param)
        self.params = ImmutableDict(params)

    def _validate_value(self, value):
        if _value_re.match(value) is None:
            raise ValueError("Invalid value: %r" % value)

    def _validate_param(self, key, value):
        return

    def to_header(self):
        header = self.value

        if self.q != 1:
            header += ';q=%s' % self.q

        for param in self.params.items():
            # TODO escaping?
            header += ';%s=%s' % param

        return header


class _Accept(object):
    range_type = None

    def __init__(self, options):
        self._options = []
        for option in options:
            if isinstance(option, str):
                option = (option,)

            self._options.append(self.range_type(*option))

    def __iter__(self):
        return iter(self._options)

    def __contains__(self, value):
        try:
            value.acceptability(self)
        except NotAcceptable:
            return False
        else:
            return True

    def __getitem__(self, value):
        try:
            return value.acceptability(self)
        except NotAcceptable as e:
            raise KeyError() from e

    def __repr__(self):
        raise NotImplementedError()

    def __str__(self):
        return self.to_header()

    def to_header(self):
        """Return an equivalent string suitable for use as an `Accept` header.
        """
        return ','.join(option.to_header() for option in self)


@functools.total_ordering
class _Acceptibility(object):
    def __init__(self, value, *, match_quality, q, qs=None):
        self._value = value
        self._match_quality = match_quality
        self._q = q
        self._qs = qs

    @property
    def exact_match(self):
        return bool(self._match_quality)

    @property
    def quality(self):
        if self._qs is not None:
            return self._q * self._qs
        return self._q

    def __eq__(self, other):
        if other is None:
            return False

        if self._match_quality != other._match_quality:
            return False

        if self.quality != other.quality:
            return False

        return True

    def __gt__(self, other):
        if other is None:
            return True

        if self._match_quality > other._match_quality:
            return True

        if self.quality > other.quality:
            return True

        return False


class _ContentTypeRange(_Range):
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


class ContentTypeAccept(_Accept):
    range_type = _ContentTypeRange


class ContentTypeAcceptibility(_Acceptibility):
    def __init__(
                self, content_type, *,
                type_matches, subtype_matches,
                q, qs=None
            ):
        super(ContentTypeAcceptibility, self).__init__(
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


class ContentType(_Value):
    match_type = ContentTypeAcceptibility

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


def _split_accept_string(string):
    for accept_range in string.split(','):
        accept, *str_params = accept_range.split(';')

        params = {}
        for param in str_params:
            try:
                key, value = param.split('=', 1)
            except ValueError as e:
                raise ValueError("invalid parameter: %r" % param) from e

            key, value = key.strip(), value.strip()

            params[key] = value

        q = params.pop('q', '1.0')

        yield accept.strip(), q, params


def parse_accept_header(string):
    """Creates a new `ContentTypeAccept` object from an `Accept` header string.
    """
    return ContentTypeAccept(_split_accept_string(string))


def parse_content_type_header(string, qs=None):
    """Creates a new `ContentType` object from a mime type string.
    """
    return ContentType(string, qs=qs)


class _LanguageRange(_Range):
    def _validate_param(self, key, value):
        raise ValueError("Accept-Language header does not take parameters")


class LanguageAccept(_Accept):
    range_type = _LanguageRange


class LanguageAcceptibility(_Acceptibility):
    def __init__(
                self, content_type, *,
                specificity, tail,
                q, qs=None
            ):
        super(LanguageAcceptibility, self).__init__(
            content_type, match_quality=(-tail, specificity), q=q, qs=qs
        )

    @property
    def language(self):
        return self._value

    @property
    def specificity(self):
        return self._match_quality[1]

    @property
    def tail(self):
        return -self._match_quality[0]

    @property
    def exact_match(self):
        return not self.tail


class Language(_Value):
    match_type = LanguageAcceptibility

    def _acceptability_for_option(self, option):
        if self.value == option.value:
            specificity = len(list(option.value.split('-')))
            tail = 0
        elif self.value.startswith('%s-' % option.value):
            specificity = len(list(option.value.split('-')))
            tail = len(list(self.value.split('-'))) - specificity
        elif option.value == '*':
            specificity = 0
            tail = len(list(self.value.split('-')))
        else:
            raise NotAcceptable()

        return self.match_type(
            self, specificity=specificity, tail=tail,
            qs=self.qs, q=option.q
        )


def parse_accept_language_header(string):
    return LanguageAccept(_split_accept_string(string))


def parse_language_header(string):
    return Language(string)


class _CharsetRange(_Range):
    def _validate_param(self, key, value):
        raise ValueError("Accept-Charset header does not take parameters")


class CharsetAccept(_Accept):
    range_type = _CharsetRange


class CharsetAcceptibility(_Acceptibility):
    def __init__(self, value, *, exact_match, q, qs=None):
        super(CharsetAcceptibility, self).__init__(
            value, match_quality=exact_match, q=q, qs=qs
        )

    @property
    def charset(self):
        return self._value

    @property
    def exact_match(self):
        return self._match_quality


class Charset(_Value):
    match_type = CharsetAcceptibility


def parse_accept_charset_header(string):
    return CharsetAccept(_split_accept_string(string))


def parse_charset_header(string):
    return Charset(string)


__all__ = [
    'ContentType', 'ContentTypeAccept',
    'parse_content_type_header', 'parse_accept_header',
    'Language', 'LanguageAccept',
    'parse_language_header', 'parse_accept_language_header',
    'Charset', 'CharsetAccept',
    'parse_charset_header', 'parse_accept_charset_header',
]
