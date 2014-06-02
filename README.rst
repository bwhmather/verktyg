.. image:: https://travis-ci.org/bwhmather/verktyg.png?branch=master
    :target: http://travis-ci.org/bwhmather/verktyg
    :alt: Build Status

Verktyg
=======

Examples
--------

Hello World

.. code:: python
    # hello.py
    from werkzeug import Response
    from verktyg import Dispatcher, Application, expose

    views = Dispatcher()


    @expose(views, 'index')
    def get_index(app, req):
        return Response('Hello world')


    def bind(app):
        app.add_views(views)


.. code:: python
    # root.py
    from werkzeug.serving import run_simple
    from verktyg.routing import Route
    from verktyg import Application


    app = Application()

    app.add_routes(
        Route('/', endpoint='index'),
    )

    import hello
    hello.bind(app)

    def run_dev_server():
        from werkzeug.serving import run_simple

        run_simple('127.0.0.1', 5000, app, use_debugger=True, use_reloader=True)

    if __name__ == '__main__':
        run_dev_server()
