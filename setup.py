# -*- coding: utf-8 -*-
"""
Verktyg
=======

A web framework based on Werkzeug.
"""
from setuptools import setup, find_packages


setup(
    name='verktyg',
    version='0.2.0',
    url='https://github.com/bwhmather/verktyg',
    license='BSD',
    author='Ben Mather',
    author_email='bwhmather@bwhmather.com',
    description='A web framework based on Werkzeug',
    long_description=__doc__,
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
        ],
    platforms='any',
    install_requires=[
        'werkzeug',
        'python-mimeparse >= 0.1.4',
        ],
    packages=find_packages(),
    include_package_data=True,
)
