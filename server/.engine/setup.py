from setuptools import setup, find_packages

setup(
    name='netbound',
    version='0.1.5',
    packages=find_packages(),
    install_requires=[
        "aiosqlite==0.20.0",
        "alembic==1.13.1",
        "annotated-types==0.6.0",
        "bcrypt==4.1.2",
        "cffi==1.16.0",
        "cryptography==42.0.5",
        "greenlet==3.0.3",
        "Mako==1.3.2",
        "MarkupSafe==2.1.5",
        "msgpack==1.0.8",
        "msgpack-types==0.2.0",
        "mypy==1.9.0",
        "mypy-extensions==1.0.0",
        "pycparser==2.21",
        "pydantic==2.6.4",
        "pydantic_core==2.16.3",
        "SQLAlchemy==2.0.28",
        "typing_extensions==4.10.0",
        "websockets==12.0"
    ],
)
