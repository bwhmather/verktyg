`Verktyg <verktyg_>`_
=====================

|build-status| |coverage|

Verktyg is a web framework built on `werkzeug`_.

It separates mapping of routes to endpoints and endpoints to handlers and provides a mechanism for dispatching on request content-type and method.

It also includes an optional application base class.
This wraps the routing system and provides a binding mechanism to allow extension.
The request and server context are kept explicit and separate.

Focus is on building api's where support for multiple content types is likely to be important, and where it doesn't make sense to use a form builder and therefore share code between ``GET`` and other methods.
For building html websites flask is probably a better choice.


Components
----------

Router
~~~~~~
Based on werkzeug routing but with method dispatch removed.

Maps from urls to endpoint identifiers


Dispatcher
~~~~~~~~~~
Chooses handler based on endpoint, request accept headers, and request, method.


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


    def bind(app):
        app.add_views(views)


.. code:: python

    # root.py
    import os
    import logging

    from werkzeug.serving import run_simple
    from verktyg.routing import Route
    from verktyg import Application


    def create_app(config=os.environ, debug=None, proxy=None):
        if debug is None:
            debug = config.get('DEBUG', False)

        if debug:
            logging.basicConfig(level=logging.DEBUG)
        else:
            logging.basicConfig()

        app = Application(debug=debug)
        app.config = config

        app.add_routes(
            Route('/', endpoint='index'),
        )

        import hello
        hello.bind(app)

        return app


    def run_dev_server():
        app = create_app(debug=True)
        from werkzeug.serving import run_simple
        run_simple('127.0.0.1', 5000, app, use_debugger=True, use_reloader=True)


    if __name__ == '__main__':
        run_dev_server()


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
