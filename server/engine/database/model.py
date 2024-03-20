from sqlalchemy.orm import DeclarativeBase
from typing import Type

class Base(DeclarativeBase):
    pass

def register_model(model: Type[Base]) -> None:
    globals()[model.__name__] = model