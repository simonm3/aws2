"""
This file is automatically generated by autosetup.py
Please edit the marked area only. Other areas will be
overwritten when autosetup is reruns.
"""

from setuptools import setup

params = dict(
    name='xdrive',
    description='Portable drive that can be moved between AWS instances',
    version='2.0.4',
    url='https://github.com/simonm3/xdrive.git',
    install_requires=['Fabric', 'Fabric3', 'boto3',
                      'botocore', 'pandas', 'pyperclip', 'requests'],
    packages=['xdrive'],
    data_files=[('./etc/xdrive', ['examples.ipynb', 'licence.txt'])],
    py_modules=[],
    include_package_data=True,
    scripts=None)

########## EDIT BELOW THIS LINE ONLY ##########

# pipreqs bug identifies this as well as the correct fabric3
params["install_requires"].remove("Fabric")

# optional but useful
params["install_requires"].append("nbextensions")

########## EDIT ABOVE THIS LINE ONLY ##########

setup(**params)
