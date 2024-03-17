# Netbound
A Python and GameMaker networking library for creating multiplayer games.

## Quick start
```bash
python -m venv server/.venv
server/.venv/Scripts/activate
pip install -r server/requirements.txt
alembic revision --autogenerate -m "Initial database"
alembic upgrade head
python -m server
```