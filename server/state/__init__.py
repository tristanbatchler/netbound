class TransitionError(Exception):
    pass

from server.state.base import BaseState
from server.state.entry import EntryState
from server.state.logged import LoggedState