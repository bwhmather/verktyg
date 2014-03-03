# -*- coding: utf-8 -*-
"""
    werkzeug_dispatch
    ~~~~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""
from werkzeug_dispatch.views import TemplateView, JsonView, ClassView
from werkzeug_dispatch.views import expose, expose_html, expose_json
from werkzeug_dispatch.dispatch import Dispatcher
from werkzeug_dispatch._version import __version__

__all__ = [
    'TemplateView', 'JsonView', 'ClassView',
    'expose', 'expose_html', 'expose_json',
    'Dispatcher',
    '__version__',
    ]
