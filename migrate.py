'''
An AWS Lambda migration function
to migrate the database
'''
import socket
import os
from alembic import config, command

### Special patch for bug on lambda with python 3.12
def patched_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
    # This ensures we handle cases where 'port' is None or a string
    numeric_port = int(port) if port else 5432
    # Return the hardcoded IP result to bypass the 3.12 DNS bug
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('172.31.11.232', numeric_port))]
### end special patch

socket.getaddrinfo = patched_getaddrinfo

current_dir = os.path.dirname(os.path.abspath(__file__))
CERT_PATH = os.path.join(current_dir, "global-bundle.pem")

def lambda_handler(event, context):
    try:
        print("Starting Alembic Migrations...")
        
        # 1. Path to your alembic.ini (assumed root)
        ini_path = "alembic.ini"
        
        # 2. Load the configuration
        cfg = config.Config(ini_path)
        
        # 3. Dynamic Configuration
        # Alembic requires a synchronous driver (psycopg2)
        db_url = os.getenv("DATABASE_URL")
        ssl_params = f"?sslmode=verify-full&sslrootcert={CERT_PATH}"
        if "?" in db_url:
            db_url += f"&sslmode=verify-full&sslrootcert={CERT_PATH}"
        else:
            db_url += ssl_params
        if "asyncpg" in db_url:
            db_url = db_url.replace("asyncpg", "psycopg2")
        if "@host=" in db_url:
            db_url = db_url.replace("@host=", "@")
        
        # Override ini settings with Lambda env variables
        cfg.set_main_option("sqlalchemy.url", db_url)
        cfg.set_main_option("script_location", "migrations") # folder name
        
        # 4. Execute Upgrade
        print(f"Upgrading database at {db_url}...")
        command.upgrade(cfg, "head")
        
        return {
            "statusCode": 200,
            "body": "Migrations completed successfully."
        }
    except Exception as e:
        print(f"Migration failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": f"Migration failed: {str(e)}"
        }