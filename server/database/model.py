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

class Player(Base):
    __tablename__ = 'players'
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'), unique=True)
    instanced_entity_id = Column(Integer, ForeignKey('instanced_entities.entity_id'), unique=True)
    user_id = Column(Integer, ForeignKey('users.id'), unique=True)
    image_index = Column(Integer, default=0)

class InstancedEntity(Base):
    __tablename__ = 'instanced_entities'
    id = Column(Integer, primary_key=True)
    entity_id = Column(Integer, ForeignKey('entities.id'))
    x = Column(Integer)
    y = Column(Integer)
