"""
    verktyg.jinja2
    ~~~~~~~~~~~~~~

    :copyright: (c) 2014 by Ben Mather.
    :license: BSD, see LICENSE for more details.
"""


def add_templates(self, *loaders):
    for loader in loaders:
        self.jinja_env.loader.loaders.append(loader)


def get_renderer(self, name):
    if isinstance(name, str):
        return self.jinja_env.get_template(name).render
    else:
        # assume callable
        return name


def bind(app, *loaders, **kwargs):
    """ Add a jinja2 environment to an application
    """
    # imported here as jinja is not required in setup.py.
    import jinja2
    app.jinja_env = jinja2.Environment(
        loader=jinja2.ChoiceLoader([]), **kwargs
    )

    app.add_method('add_templates', add_templates)
    app.add_method('get_renderer', get_renderer)

    app.add_templates(*loaders)
