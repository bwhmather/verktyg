from functools import singledispatch
from werkzeug.errors import HTTPException


class ExceptionRenderer(object):

    def __init__(self):
        @singledispatch
        def default(exception, app, request):
            raise NotImplementedError(exception, app, request)

        self._exception_renderer

    def add(self, exception_class, handler):
        """ Bind a function to render exceptions of the given class and all
        sub classes.

        Exception renderers take three arguments:
          * a reference to the application
          * a request object
          * the exception to be rendered
        """
        @self._exception_renderer.register(exception_class)
        def wrapper(exception, app, request):
            return handler(app, request, exception)

    def __call__(self, app, request, exception):
        return self._exception_renderer(app, request, exception)


def default_exception_renderer():
    h = ExceptionRenderer()

    @h.add(Exception)
    def handle_basic(app, request, exception):
        pass

    @h.add(HTTPException)
    def handle_http(app, request, exception):
        pass


def render():
    pass


def render_default_exception(app, request, exception):
    return render(
        app, request,
        dict(
            status=500,
            type=exception.__class__.__name__,
            description='Internal server error',
        )
    )


def render_http_exception(app, request, exception):
    return render(
        app, request,
        dict(
            status=exception.code,
            type=exception.__class__.__name__,
            description=exception.description,
        )
    )
