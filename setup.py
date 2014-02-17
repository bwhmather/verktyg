# -*- coding: utf-8 -*-
"""
Werkzeug Dispatch
=================

A simple dispatcher for werkzeug.
"""


from setuptools import setup


setup(
    name='werkzeug_dispatch',
    version='0.0.1-dev',
    url='https://github.com/bwhmather/werkzeug_dispatch',
    license='BSD',
    author='Ben Mather',
    author_email='bwhmather@bwhmather.com',
    description='A package for registering and looking up request handlers',
    long_description=__doc__,
    classifiers=[
        'Programming Language :: Python :: 3',
        ],
    install_requires=[
        'werkzeug',
        ],
    packages=['werkzeug_dispatch', 'werkzeug_dispatch.testsuite'],
    include_package_data=True,
    test_suite='werkzeug_dispatch.testsuite.suite',
    )
