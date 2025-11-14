import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

try:
    connection = pymysql.connect(
        host=os.getenv("GOOGLE_SQL_HOST"),
        user=os.getenv("GOOGLE_SQL_USER"),
        password=os.getenv("GOOGLE_SQL_PASSWORD"),
        database=os.getenv("GOOGLE_SQL_DATABASE"),
        charset='utf8mb4',
        connect_timeout=10
    )
    print("Database connection successful!")
    connection.close()
except Exception as e:
    print(f"Database connection failed: {e}")