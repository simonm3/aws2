"""
This file is automatically generated by the autogen package.
Please edit the marked area only. Other areas will be
overwritten when autogen is rerun.
"""

from setuptools import setup

params = dict(
    name='aws2',
    description='Automate AWS spot instances',
    version='0.2.5',
    url='https://github.com/simonm3/aws2.git',
    install_requires=['PyYAML', 'boto3', 'fabric',
                      'pandas', 'pyperclip', 'requests'],
    packages=['aws2'],
    package_data={'aws2': ['default.yaml']},
    include_package_data=True,
    py_modules=[],
    scripts=None)

########## EDIT BELOW THIS LINE ONLY ##########


########## EDIT ABOVE THIS LINE ONLY ##########

setup(**params)
