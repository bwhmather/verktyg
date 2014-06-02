import jinja2

from werkzeug.utils import cached_property


class Jinja2ApplicationMixin(object):
    @cached_property
    def jinja_env(self):
        return jinja2.Environment(loader=jinja2.ChoiceLoader([]))

    def add_templates(self, loader):
        self.jinja_env.loader.loaders.append(loader)

    def get_renderer(self, name):
        if isinstance(name, str):
            return self.jinja_env.get_template(name).render
        else:
            # assume callable
            return name
