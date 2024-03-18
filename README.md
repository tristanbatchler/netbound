# Netbound
A Python and GameMaker networking library for creating multiplayer games.

## Quick start
```bash
# Setup virtualenv and install dependencies
python -m venv server/.venv
server/.venv/Scripts/activate
pip install -r server/requirements.txt

# Setup SSL certificate and key (requires openssl)
openssl req -x509 -sha256 -nodes -newkey rsa:2048 -days 365 -keyout server/app/ssl/key.pem -out server/app/ssl/cert.pem -subj "/C=AU/ST=Queensland/L=Brisbane/O=Tristan Batchler/CN=localost"

# Setup database
alembic revision --autogenerate -m "Initial database"
alembic upgrade head

# Run server
python -m server
```