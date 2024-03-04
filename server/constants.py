from typing import Literal
tb_params: tuple[int, Literal["big", "little"]] = (16, "big")

EVERYONE: bytes = (0).to_bytes(*tb_params)
ONLY_CLIENT: bytes = (1).to_bytes(*tb_params)
ONLY_PROTO: bytes = (2).to_bytes(*tb_params)