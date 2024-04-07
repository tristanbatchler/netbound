from __future__ import annotations
from typing import Type

def unique(class_: Type[GameObject]) -> Type[GameObject]:
    """A decorator that ensures that only one instance of the class is stored in the GameObjectsSet. 
    Subsequent additions of the same type to the GameObjectsSet will overwrite the previous instance."""
    class_.unique_class = True
    return class_

class GameObjectsSet:
    def __init__(self) -> None:
        self._objects: set[GameObject] = set()
        self._unique_objects: dict[Type[GameObject], GameObject] = {}

    def get_unique(self, class_: Type[GameObject]) -> GameObject | None:
        """Get the unique object of the specified class, if it exists."""
        return self._unique_objects.get(class_, None)

    def add(self, obj: GameObject) -> None:
        """Add an object to the set of game objects. If the object is unique, it will overwrite any 
        existing object of the same type."""
        if obj is None:
            return
        if obj.unique_class:
            self._objects = {o for o in self._objects if not isinstance(o, type(obj))}
            self._unique_objects[type(obj)] = obj
        self._objects.add(obj)

    def discard(self, obj: GameObject) -> None:
        """Remove an object from the set of game objects, if it exists. If the object is unique, this 
        method will remove any existing object of the same type."""
        if obj is None:
            return
        self._objects.discard(obj)
        if obj.unique_class:
            self._unique_objects.pop(type(obj), None)

    def __iter__(self):
        return iter(self._objects)
    
    def copy(self):
        return self._objects.copy()


class GameObject:
    """
    An object that belongs specifically to the game, but is not a player or something that necessarily 
    belongs to the database. It is something that is created and destroyed during the course of a game, 
    like a projectile. The update method is called by the server at every game frame (e.g. 60 times per 
    second) to update the object's state. Therefore, the update logic should be kept as lightweight as 
    possible.

    To indicate that only one instance of this class should be stored in the GameObjectsSet, decorate 
    the class with the `unique` decorator.
    """
    unique_class: bool = False
    def update(self, delta: float):
        """
        Update the state of the object. This method is called by the server at every game frame, so it 
        should be kept as lightweight as possible.
        """
        pass
