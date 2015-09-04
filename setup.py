"""
Verktyg
=======

A web framework based on Werkzeug.
"""
from setuptools import setup, find_packages

extras_require = {
}

setup(
    name='verktyg',
    version='0.8.3',
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
        'werkzeug >= 0.10, < 0.11',
    ],
    tests_require=list(set(sum(
        (extras_require[extra] for extra in {}), []
    ))),
    extras_require=extras_require,
    packages=find_packages(),
    include_package_data=True,
    test_suite='verktyg.testsuite.suite',
)
