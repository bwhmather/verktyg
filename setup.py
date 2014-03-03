# -*- coding: utf-8 -*-
"""
Werkzeug Dispatch
=================

A simple dispatcher for werkzeug.
"""

import re
import os
import ast
import subprocess

from setuptools import setup


version_template = '''# -*- coding: utf-8 -*-
"""
Automatically generated using `git describe` in `setup.py`
"""

__version__ = {version}
'''

version_path = os.path.join(
    os.path.dirname(__file__),
    'werkzeug_dispatch', '_version.py'
)

try:
    # attempt to determine version from git
    version = subprocess.check_output(["git", "describe"])
    version = version.decode('utf-8').strip()

    # record version
    with open(version_path, 'w') as version_file:
        version_file.write(version_template.format(version=repr(version)))
except:
    # read version from previously written _version.py file
    with open(version_path, 'r') as version_file:
        version_escaped = re.search(
            r"__version__\s*=\s*(.*)",
            version_file.read()
        ).group(1)
        version = ast.literal_eval(version_escaped)

setup(
    name='werkzeug_dispatch',
    version=version,
    url='https://github.com/bwhmather/werkzeug_dispatch',
    license='BSD',
    author='Ben Mather',
    author_email='bwhmather@bwhmather.com',
    description='A package for registering and looking up request handlers',
    long_description=__doc__,
    classifiers=[
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Operating System :: OS Independent',
        'Programming Language :: Python :: 3',
        'Topic :: Internet :: WWW/HTTP :: Dynamic Content',
        'Topic :: Software Development :: Libraries :: Python Modules',
        ],
    install_requires=[
        'werkzeug',
        ],
    packages=['werkzeug_dispatch', 'werkzeug_dispatch.testsuite'],
    include_package_data=True,
    test_suite='werkzeug_dispatch.testsuite.suite',
    )
