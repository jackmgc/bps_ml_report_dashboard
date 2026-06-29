"""Database configuration - reads from .env file"""
import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Database configuration
DB_CONFIG = {
    'host': os.getenv('PSQL_HOST', 'localhost'),
    'port': int(os.getenv('PSQL_PORT', 5432)),
    'user': os.getenv('PSQL_USER'),
    'password': os.getenv('PSQL_PASSWORD'),
    'database': os.getenv('PSQL_DBNAME', 'skripsi'),
}

# Validate critical configuration
if not DB_CONFIG['user']:
    raise ValueError("PSQL_USER not configured in .env file")

if DB_CONFIG['password'] is None or DB_CONFIG['password'] == '':
    raise ValueError("PSQL_PASSWORD not configured in .env file. Please update .env with your PostgreSQL password.")

# File paths
DATA_FOLDER = os.getenv('DATA_FOLDER', './data')
REPORTS_FOLDER = os.getenv('REPORTS_FOLDER', './reports')

# ETL configuration
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
RECONCILIATION_TOLERANCE = float(os.getenv('RECONCILIATION_TOLERANCE', '0.0001'))

# Build PostgreSQL connection string (URL-encode password for special characters)
PSQL_CONNECTION_STRING = (
    f"postgresql+psycopg2://{DB_CONFIG['user']}:{quote_plus(DB_CONFIG['password'])}"
    f"@{DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['database']}"
    f"?client_encoding=utf8"
)
