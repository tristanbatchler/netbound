class GameObject:
    """
    An object that belongs specifically to the game, but is not a player or something that necessarily 
    belongs to the database. It is something that is created and destroyed during the course of a game, 
    like a projectile. The update method is called by the server at every game frame (e.g. 60 times per 
    second) to update the object's state. Therefore, the update logic should be kept as lightweight as 
    possible.
    """
    def __init__(self):
        self.freed: bool = False 

    def update(self):
        """
        Update the state of the object. This method is called by the server at every game frame, so it 
        should be kept as lightweight as possible.
        """
        pass

    def queue_free(self):
        """
        Queues the object for deletion. This method should be called when the object is no longer needed 
        and can be safely removed from the server's game objects set (i.e. this will be removed from 
        all states' `_game_objects` set at the next game frame).
        """
        self.freed = True