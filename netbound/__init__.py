"""
A safe and fair way to play games with friends over the internet
"""

from typing import Coroutine, Any
from asyncio import ensure_future, get_event_loop, TimerHandle, AbstractEventLoop

def schedule(timeout: float, coro: Coroutine[Any, Any, None]) -> TimerHandle:
    """
    Schedule a coroutine to run after a certain amount of time (in seconds). This will ensure that 
    the awaitable is performed in a non-blocking manner. 

    This function returns an `asyncio.TimeHandle` object, which can be cancelled by calling e.g.
    ```
    handle: TimerHandle = schedule(5, my_coro)
    handle.cancel()
    ```

    This will cancel the scheduled coroutine from running, if it hasn't run already, but it will not 
    cancel the coroutine if it is already running.
    """
    loop: AbstractEventLoop = get_event_loop()
    return loop.call_later(timeout, lambda: ensure_future(coro()))
