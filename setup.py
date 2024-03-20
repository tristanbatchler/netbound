from setuptools import setup, find_packages

with open("requirements.txt", 'r') as f:
    dependencies = f.readlines()

setup(
    name='netbound',
    version='0.1.6',
    packages=find_packages(),
    install_requires=dependencies,
)
