#!/usr/bin/env python

""" this is a generic conf.py that uses sensible defaults for most projects

no need to change this file. override in confplus.py which is imported at the bottom of this file
"""
import sys
from os.path import join, basename
from datetime import datetime

try:
    import win32api
except:
    # windows only
    pass
from pipreqs import pipreqs
import importlib
from glob import glob
import os

#####################
# Project information
#####################

# author from username
try:
    # windows full name
    author = win32api.GetUserNameEx(3)
except:
    # gitlab CI full name of user that started the job
    author = os.environ.get("GITLAB_USER_NAME", "")

# project name from root folder
copyright = ", ".join([str(datetime.now().year), author])
root = os.path.abspath(join(__file__, os.pardir, os.pardir))
project = basename(root)

# version from first <version.py>.__version__
try:
    versionfiles = glob(f"{root}/**/version.py", recursive=True)
    sys.path.insert(0, os.path.dirname(versionfiles[0]))
    version = importlib.__import__("version").__version__
except:
    version = "latest"

# mock all imports that are not installed so packages can be imported without errors
# e.g. a package that subprocess_run in a container may not have dependencies installed locally
imports = pipreqs.get_all_imports(root)
autodoc_mock_imports = [f for f in imports if importlib.util.find_spec(f) is None]

########
# layout
########

# concatenate docstrings for class and __init__
autoclass_content = "both"

# same as python. better than the default theme.
html_theme = "sphinx_rtd_theme"

# includes the todos in the docs
todo_include_todos = True

# not needed in docs
exclude_patterns = ["_rst/setup.rst", ".ipynb_checkpoints/*"]

############
# extensions
############

extensions = [
    "sphinx.ext.autodoc",  # source code docstrings
    "sphinx.ext.intersphinx",  # links to other package docs
    "sphinx.ext.todo",  # enable todo_boxes
    "sphinx.ext.coverage",  # report docstring coverage
    "sphinx.ext.viewcode",  # link to source code
    "sphinx.ext.githubpages",  # enable githubpages
    "nbsphinx",  # insert views of jupyter notebooks in the docs
]
# maps links to docs for other packages
intersphinx_mapping = {"python": ("https://docs.python.org/3", None)}

# more config options can be added in confplus.py
try:
    from .confplus import *
except KeyError:
    pass
