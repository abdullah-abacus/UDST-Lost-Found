import os
from google.cloud.sql.connector import Connector, IPTypes
import pg8000
import sqlalchemy
from sqlalchemy import text
from dotenv import load_dotenv

load_dotenv()

POSTGRES_USER = os.getenv('POSTGRES_USER')
SQL_INSTANCE_NAME = os.getenv('SQL_INSTANCE_NAME')
POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD')
POSTGRES_DB = os.getenv('POSTGRES_DB')
POSTGRES_HOST = os.getenv('POSTGRES_HOST')
POSTGRES_PORT = os.getenv('POSTGRES_PORT')
TABLE_NAME = os.getenv('TABLE_NAME')

print("Connecting to the database with the following parameters:")
print(f"User: {POSTGRES_USER}, Host: {POSTGRES_HOST}, Port: {POSTGRES_PORT}, DB: {POSTGRES_DB}, Table_Name: {TABLE_NAME}")

def connect_with_connector() -> sqlalchemy.engine.base.Engine:
    instance_connection_name = SQL_INSTANCE_NAME
    db_user = POSTGRES_USER
    db_pass = POSTGRES_PASSWORD
    db_name = POSTGRES_DB
    
    if os.environ.get("PRIVATE_IP"):
        ip_type = IPTypes.PRIVATE
    else:
        ip_type = IPTypes.PUBLIC
    
    connector = Connector()
    
    def getconn() -> pg8000.dbapi.Connection:
        conn: pg8000.dbapi.Connection = connector.connect(
            instance_connection_name,
            "pg8000",
            user=db_user,
            password=db_pass,
            db=db_name,
            ip_type=ip_type,
        )
        return conn
    
    pool = sqlalchemy.create_engine(
        "postgresql+pg8000://",
        creator=getconn,
    )
    return pool

def get_db_connection():
    return connect_with_connector()

def run_query(query):
    conn = get_db_connection()
    query = text(query)
    with conn.connect() as conn:
        result = conn.execute(query)
        print("Query executed successfully.")
        print("Results: ", result.fetchall())
    return result

if __name__ == "__main__":
    run_query("SELECT VERSION()")
