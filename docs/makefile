# windows/linux makefile for Sphinx documentation

.PHONY:  all clean rst html

all:
	make clean rst html

# delete existing output. optional.
clean:
	rm -rf _rst
	rm -rf _build

# create directives for docstrings in docs/_rst/*.rst
# if you have multiple projects then repeat this line replacing .. with root folder for each project
rst:
	sphinx-apidoc -f -o _rst ..

# create html
html:
	sphinx-build -M html . _build
