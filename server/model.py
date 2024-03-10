from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import DeclarativeBase
from typing import Type

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    password = Column(String)

class Entity(Base):
    __tablename__ = 'entities'
    id = Column(Integer, primary_key=True)
    name = Column(String)

class InstancedEntity(Base):
    __tablename__ = 'instanced_entities'
    entity_id = Column(Integer, ForeignKey('entities.id'), primary_key=True)
    x = Column(Integer)
    y = Column(Integer)
