"""Helper functions for ETL pipeline"""
import os
import pandas as pd
import psycopg2
from psycopg2.extras import execute_batch
from sqlalchemy import create_engine, text
from config.constants import CANONICAL_PROVINCES
from utils.logger import get_logger

logger = get_logger(__name__)

def validate_province(province_name):
    """
    Validate if province name is in canonical list.
    
    Args:
        province_name (str): Province name to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return province_name in CANONICAL_PROVINCES

def get_all_valid_provinces():
    """Get list of all valid provinces"""
    return CANONICAL_PROVINCES.copy()

def execute_sql_script(engine, script_path):
    """
    Execute SQL script from file using SQLAlchemy.
    
    Args:
        engine: SQLAlchemy engine
        script_path (str): Path to SQL script file
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        # Try utf-8-sig first (strips BOM if present), then fallback to utf-8
        try:
            with open(script_path, 'r', encoding='utf-8-sig') as f:
                sql_script = f.read()
        except UnicodeDecodeError:
            with open(script_path, 'r', encoding='utf-8', errors='replace') as f:
                sql_script = f.read()
        
        # Split by semicolon and execute each statement
        statements = [stmt.strip() for stmt in sql_script.split(';') if stmt.strip()]
        
        with engine.connect() as conn:
            for statement in statements:
                if statement:
                    conn.execute(text(statement))
            conn.commit()
        
        logger.info(f"[OK] Executed SQL script: {script_path}")
        return True
    except Exception as e:
        logger.error(f"[FAIL] Error executing SQL script {script_path}: {str(e)}")
        return False

def read_sql_file(script_path):
    """
    Read SQL script from file.
    
    Args:
        script_path (str): Path to SQL script file
        
    Returns:
        str: SQL script content
    """
    try:
        # Try utf-8-sig first (strips BOM if present), then fallback to utf-8
        try:
            with open(script_path, 'r', encoding='utf-8-sig') as f:
                return f.read()
        except UnicodeDecodeError:
            with open(script_path, 'r', encoding='utf-8', errors='replace') as f:
                return f.read()
    except Exception as e:
        logger.error(f"[FAIL] Error reading SQL file {script_path}: {str(e)}")
        return None

def bulk_insert_dataframe(engine, df, table_name, schema_name, if_exists='append', chunksize=5000):
    """
    Bulk insert DataFrame into PostgreSQL table.
    
    Args:
        engine: SQLAlchemy engine
        df (pd.DataFrame): DataFrame to insert
        table_name (str): Target table name
        schema_name (str): Schema name
        if_exists (str): 'append', 'replace', or 'fail'
        chunksize (int): Chunk size for insertion
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        logger.info(f"Inserting {len(df)} rows into {schema_name}.{table_name}...")
        df.to_sql(
            table_name,
            engine,
            schema=schema_name,
            if_exists=if_exists,
            index=False,
            chunksize=chunksize,
            method='multi'
        )
        logger.info(f"[OK] Successfully inserted {len(df)} rows into {schema_name}.{table_name}")
        return True
    except Exception as e:
        logger.error(f"[FAIL] Error inserting into {schema_name}.{table_name}: {str(e)}")
        return False

def query_database(engine, sql_query):
    """
    Execute query and return results as DataFrame.
    
    Args:
        engine: SQLAlchemy engine
        sql_query (str): SQL query
        
    Returns:
        pd.DataFrame: Query results
    """
    try:
        return pd.read_sql(sql_query, engine)
    except Exception as e:
        logger.error(f"[FAIL] Error executing query: {str(e)}")
        return None

def file_exists(file_path):
    """Check if file exists"""
    return os.path.exists(file_path)

def ensure_directory(directory_path):
    """Create directory if it doesn't exist"""
    os.makedirs(directory_path, exist_ok=True)
