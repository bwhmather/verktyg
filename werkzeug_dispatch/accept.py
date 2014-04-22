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
