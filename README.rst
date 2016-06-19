`Verktyg <verktyg_>`_
=====================

|build-status| |coverage|

Verktyg is a magic free python web framework focused on making it easy to build large APIs.

It started out as a replacement routing layer for `werkzeug`_ but has slowly developed into a full fork.

Unlike `werkzeug_`, it separates mapping of routes to endpoints and endpoints to handlers and provides a mechanism for dispatching on request content-type and method.

For form based websites, where the coupling of ``GET`` and ``POST`` handlers makes more sense, `werkzeug`_ and `flask`_ will probably always be the better choice.


Components
----------

Verktyg separates the mapping from routes to endpoints from the mapping from the mapping from endpoints to handlers.

This allows handlers to be defined without having to be aware of where they are bound, which means that APIs can be described centrally but have their implementation split out into separate modules.

Router
~~~~~~
Based on werkzeug routing but with method dispatch removed.

Maps from urls to endpoint identifiers.


Dispatcher
~~~~~~~~~~
Chooses a handler for a request based on the endpoint chosen by the router, the request method, and the request accept headers.


Application
~~~~~~~~~~~
Wraps dispatcher and router

Binds together request parsing, routing, dispatch, and error handling.


Examples
--------

A slightly overcomplicated Hello World application.
Tries to illustrate separate route configuration and implementation.

.. code:: python

    # hello.py
    from werkzeug import Response
    from verktyg import Dispatcher, Application, expose

    views = Dispatcher()


    @expose(views, 'index')
    def get_index(app, req):
        return Response('Hello world')


    def bind(builder):
        builder.add_views(views)


.. code:: python

    # root.py
    import os
    import logging

    from werkzeug.serving import run_simple
    from verktyg.routing import Route
    from verktyg import Application


    def create_app(config=os.environ, debug=None):
        if debug is None:
            debug = config.get('DEBUG', False)

        if debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig()

        builder = ApplicationBuilder(debug=debug)

        builder.add_routes(
            Route('/', endpoint='index'),
        )

        import verktyg_sqlalchemy
        verktyg_sqlalchemy.bind(
            builder, database_url=config['APP_DB_URL'],
        )

        import hello
        hello.bind(builder)

        app = builder(config.get('APP_PUBLIC_URL', ''))
        app.debug = debug

        return app


    def _server_main():
        import verktyg_server.argparse

        parser = argparse.ArgumentParser(description="Run the example app")
        verktyg.server.argparse.add_arguments(parser)
        args = parser.parse_args()

        app = create_app(debug=True)

        server = verktyg_server.argparse.make_server(args)
        return server


    if __name__ == '__main__':
        _server_main()


Bugs
----

Please post any problems or feature requests using the `issue tracker <issues_>`_


.. |build-status| image:: https://travis-ci.org/bwhmather/verktyg.png?branch=master
    :target: http://travis-ci.org/bwhmather/verktyg
    :alt: Build Status
.. |coverage| image:: https://coveralls.io/repos/bwhmather/verktyg/badge.png?branch=develop
    :target: https://coveralls.io/r/bwhmather/verktyg?branch=develop
    :alt: Coverage
.. _verktyg: https://github.com/bwhmather/verktyg
.. _werkzeug: https://github.com/mitsuhiko/werkzeug
.. _issues: https://github.com/bwhmather/verktyg/issues
