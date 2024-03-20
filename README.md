# Netbound
A safe and fair way to play games with friends over the internet

## ⚡ Quick start

### Setup virtualenv and install dependencies
```powershell
python -m venv server/.venv
server/.venv/Scripts/activate
pip install -r server/requirements.txt
```


### Create SSL certificate and key (requires openssl)
1. Become a certificate authority
    ```powershell
    cd server/core/app/ssl
    # Generate private key (prompted passcode should be memorable, and at least 4 characters long)
    openssl genrsa -des3 -out myCA.key 2048
    # Generate root certificate (prompted passcode should be the same as the private key)
    openssl req -x509 -new -nodes -key myCA.key -sha256 -days 825 -out myCA.pem
    ```

    You will be prompted to fill in some information. Here, I just filled in as much relevant information as I could, even making up some information where I didn't have any. The most important thing is to ensure `localhost` is in the "Common Name" field.

1. Create a certificate for the server, which falls under our CA
    1. Run the following command to create a new private key and certificate-signing request
    ```powershell
    cd server/core/app/ssl
    # Generate a private key
    openssl genrsa -out localhost.key 2048
    # Create a certificate-signing request
    openssl req -new -key localhost.key -out localhost.csr
    ```
    
    You will be prompted to fill in some information here again. I just repeated the same information I used for the CA certificate, again ensuring `localhost` is in the "Common Name" field. 
    
    Run the following command to create the certificate:
    ```powershell
    openssl x509 -req -in localhost.csr -CA myCA.pem -CAkey myCA.key -CAcreateserial -out localhost.crt -days 825 -sha256 -extfile localhost.ext
    ```

    You will be prompted to enter the passcode for the CA private key. This will create a certificate file called `localhost.crt`.

1. Verify the certificate (optional)
    ```powershell
    openssl verify -CAfile myCA.pem -verify_hostname localhost localhost.crt
    ```

    If the certificate is valid, you should see `localhost.crt: OK`.


### 👩‍💻 **For Windows users only** 
> ### Allow `.exe` and HTML5 exports on Edge to connect to the server
> 
> 1. First run the following command in the `ssl` directory to convert our CA cert to a `.pfx` file which Windows can readily install
>    ```powershell
>    openssl pkcs12 -export -out myCA.pfx -inkey myCA.key -in myCA.pem
>    ```
>
> 1. Now import the `myCA.pfx` into the Trusted Certificate Authorities of Windows by opening (double-click) the `myCA.pfx` file, selecting "Local Machine" and "Next", "Next" again, enter the password and then "Next", and select "Place all certificates int he following store:" and click on Browse and choose "Trusted Root Certification Authorities" and Next, and then "Finish".
>


### 💻 **For Mac users only**
> ### Allow `.app` and HTML5 exports on Safari to connect to the server
>
> 1. Import the CA cert at "File > Import file", then also find it in the list, right click it, expand "> Trust", and select "Always"
> 1. Add `extendedKeyUsage=serverAuth,clientAuth below basicConstraints=CA:FALSE`, and make sure you set the "CommonName" to `localhost` when it asks for setup.
>


### 🦊 **For Firefox users only**
> Go to <a href="about:preferences#privacy" target="_blank">about:preferences#privacy</a>, scroll down to "Certificates", click "View Certificates", go to "Authorities", click "Import", select the `myCA.pem` file, click "Open", click "OK"


### 🌐 **For Chrome users only**
> Go to <a href="chrome://settings/security" target="_blank">chrome://settings/security</a>, scroll down to "Security", click "Manage certificates", go to "Trusted Root Certification Authorities", click "Import", select the `myCA.pem` file, click "Next", click "Finish", click "Yes" when prompted


### Setup database
```powershell
alembic revision --autogenerate -m "Initial database"
alembic upgrade head
```

### Run the server
```powershell
python -m server
```