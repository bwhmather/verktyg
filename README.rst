.. image:: https://travis-ci.org/bwhmather/werkzeug_dispatch.png?branch=master
    :target: http://travis-ci.org/bwhmather/werkzeug_dispatch
    :alt: Build Status

Werkzeug Dispatch
=================

Examples
--------

Hello World

.. code:: python

    from werkzeug import Response
    from werkzeug.routing import Map, Rule
    from werkzeug.serving import run_simple
    from werkzeug_dispatch import Dispatcher, Application, expose

    url_map = Map([
        Rule('/',
             endpoint='index'),
        ])

    dispatcher = Dispatcher()


    @expose(dispatcher, 'index')
    def get_index(app, req):
        return Response('Hello world')


    app = Application(url_map, dispatcher)
    run_simple('127.0.0.1', 5000, app, use_debugger=True, use_reloader=True)


Slightly more idiomatic hello world

.. code:: python

    from werkzeug import Response
    from werkzeug.routing import Map, Rule
    from werkzeug_dispatch import Dispatcher, Application, expose

    url_map = Map([
        Rule('/',
             endpoint='index'),
        ])

    dispatcher = Dispatcher()


    @expose(dispatcher, 'index')
    def get_index(app, req):
        return Response('Hello world')


    def create_app(global_config, **local_config):
        app_config = dict(global_config or {})
        app_config.update(local_config)

        application = Application(url_map, dispatcher)
        application.config = app_config

        return application


    if __name__ == '__main__':
        from werkzeug.serving import run_simple

        app = create_app({})
        run_simple('127.0.0.1', 5000, app, use_debugger=True, use_reloader=True)
