"""
This file is automatically generated by autosetup.py
Please edit the marked area only. Other areas will be
overwritten when autosetup is reruns.
"""

from setuptools import setup

params = dict(
    name='aws2',
    description='Introduction',
    version='0.2.1',
    url='https://github.com/simonm3/aws2.git',
    install_requires=['Fabric', 'Fabric3', 'boto3',
                      'botocore', 'pandas', 'pyperclip', 'requests'],
    packages=['aws2'],
    data_files=[
        ('./etc/aws2', ['examples.ipynb', 'licence.txt', 'readme.md', 'version'])],
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
