from setuptools import setup, find_packages

from pathlib import Path
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()
dependencies = (this_directory / "requirements.txt").read_text().splitlines()

setup(
    name='netbound',
    version='0.1.13',
    packages=find_packages(),
    url='https://github.com/tristanbatchler/netbound',
    install_requires=dependencies,
    license='MIT',
    author='Tristan Batchler',
    long_description=long_description,
    long_description_content_type='text/markdown'
)
