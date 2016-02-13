"""
    verktyg.accept._base
    ~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2016 Ben Mather
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


# TODO better name
class Value(object):
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


class Range(object):
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

    def __repr__(self):
        return '{name}(value={value!r}, q={q!r}, params={params!r})'.format(
            name=self.__class__.__name__,
            value=self.value,
            q=self.q,
            params=self.params,
        )

    def __str__(self):
        return self.to_header()

    def to_header(self):
        header = self.value

        if self.q != 1:
            header += ';q=%s' % self.q

        for param in self.params.items():
            # TODO escaping?
            header += ';%s=%s' % param

        return header


class Accept(object):
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
class Acceptability(object):
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


def split_accept_string(string):
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
