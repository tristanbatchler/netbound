# Netbound
A Python and GameMaker networking library for creating multiplayer games.

## Quick start

1. Setup virtualenv and install dependencies
    ```powershell
    python -m venv server/.venv
    server/.venv/Scripts/activate
    pip install -r server/requirements.txt
    ```

1. Setup SSL certificate and key (requires openssl)
    ```powershell
    openssl req -x509 -sha256 -nodes -newkey rsa:2048 -days 3650 -keyout server/app/ssl/key.pem -out server/app/ssl/cert.cer -subj "/C=AU/ST=Queensland/L=Brisbane/O=Tristan Batchler/CN=localost"
    ```

1. Install the certificate on your machine
    ```powershell
    certutil -addstore -user -f "ROOT" server/app/ssl/cert.cer  # Click "Yes" when prompted
    ```

1. For HTML5 exports, you will need to install the certificate on the browser (depending on the browser)
   * For **Edge**, got to edge://settings/privacy, scroll down to "Security", click "Manage certificates", go to "Trusted Root Certification Authorities", click "Import", select the cert.cer file, click "Next", select "Place all certificates in the following store" with "Trusted Root Certification Authorities", click "Next", click "Finish", click "Yes" when prompted
   * For **Firefox**, go to about:preferences#privacy, scroll down to "Certificates", click "View Certificates", go to "Authorities", click "Import", select the cert.cer file, click "Open", click "OK"
   * For **Chrome**, go to chrome://settings/security, scroll down to "Security", click "Manage certificates", go to "Trusted Root Certification Authorities", click "Import", select the cert.cer file, click "Next", click "Finish", click "Yes" when prompted

1. Setup database
    ```powershell
    alembic revision --autogenerate -m "Initial database"
    alembic upgrade head
    ```

1. Run the server
    ```powershell
    python -m server
    ```