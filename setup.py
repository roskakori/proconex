"""
Installer for proconex.

Developer cheat sheet
---------------------

Create the installer archive::

  $ python setup.py sdist --formats=zip

Upload release to PyPI::

  $ python proconex.py
  $ python test/test_proconex.py
  $ python setup.py sdist --formats=zip upload

Tag a release::

  $ git tag -a -m "Tagged version 1.x." v1.x
  $ git push --tags
"""
# Copyright (C) 2012 Thomas Aglassinger
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or (at your
# option) any later version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
# FITNESS FOR A PARTICULAR PURPOSE.  See the GNU Lesser General Public
# License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
from distutils.core import setup

import proconex

setup(
    name="proconex",
    version=proconex.__version__,
    py_modules=["proconex"],
    description="producer/consumer with exception handling",
    keywords="xml output stream large big huge namespace unicode memory footprint",
    author="Thomas Aglassinger",
    author_email="roskakori@users.sourceforge.net",
    url="http://pypi.python.org/pypi/proconex/",
    license="GNU Lesser General Public License 3 or later",
    long_description=proconex.__doc__, #@UndefinedVariable
    classifiers=[
        "Development Status :: 4 - Beta",
        "Environment :: Plugins",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)",
        "Natural Language :: English",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 2.5",
        "Programming Language :: Python :: 2.6",
        "Programming Language :: Python :: 2.7",
        "Topic :: Software Development :: Libraries",
    ],
)
