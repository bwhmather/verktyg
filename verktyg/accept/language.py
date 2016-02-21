"""
    verktyg.accept.language
    ~~~~~~~~~~~~~~~~~~~~~~~

    :copyright:
        (c) 2016 Ben Mather
    :license:
        BSD, see LICENSE for more details.
"""
from verktyg.exceptions import NotAcceptable

from verktyg.accept import _base


class _LanguageRange(_base.Range):
    def _validate_param(self, key, value):
        raise ValueError("Accept-Language header does not take parameters")


class LanguageAccept(_base.Accept):
    range_type = _LanguageRange


class LanguageAcceptability(_base.Acceptability):
    def __init__(
                self, content_type, *,
                specificity, tail,
                q, qs=None
            ):
        super(LanguageAcceptability, self).__init__(
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


class Language(_base.Value):
    match_type = LanguageAcceptability

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
    return LanguageAccept(_base.split_accept_string(string))


def parse_language_header(string):
    return Language(string)
