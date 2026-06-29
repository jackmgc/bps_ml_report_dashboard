"""Loader module - loads data to PostgreSQL using pure Python (no SQL files)"""
import os
import pandas as pd
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.exc import SQLAlchemyError
from config.db_config import PSQL_CONNECTION_STRING
from utils.logger import get_logger

# Set encoding environment variables BEFORE any database connections
os.environ['PGCLIENTENCODING'] = 'UTF8'
os.environ['PYTHONIOENCODING'] = 'utf-8'

logger = get_logger(__name__)

# DDL statements as Python strings
CREATE_STAGING_SCHEMA ="""
DROP SCHEMA IF EXISTS staging CASCADE;
CREATE SCHEMA IF NOT EXISTS staging;
"""

CREATE_STAGING_TABLE = """
CREATE TABLE IF NOT EXISTS staging.indikator_raw (
    id SERIAL PRIMARY KEY,
    provinsi VARCHAR(255) NOT NULL,
    tahun INTEGER NOT NULL,
    kategori VARCHAR(255),
    indikator VARCHAR(255) NOT NULL,
    dimensi VARCHAR(255),
    nilai NUMERIC(15, 4),
    satuan VARCHAR(100),
    is_national_aggregate BOOLEAN DEFAULT FALSE,
    sumber VARCHAR(255),
    data_kualitas_flag VARCHAR(20),
    catatan TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_staging_provinsi ON staging.indikator_raw(provinsi);
CREATE INDEX IF NOT EXISTS idx_staging_tahun ON staging.indikator_raw(tahun);
CREATE INDEX IF NOT EXISTS idx_staging_indikator ON staging.indikator_raw(indikator);
"""

CREATE_VALIDATION_TABLE = """
CREATE TABLE IF NOT EXISTS staging.validation_report (
    id SERIAL PRIMARY KEY,
    check_type VARCHAR(255) NOT NULL,
    status VARCHAR(50),
    details TEXT,
    row_count INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DW_SCHEMA = """
DROP SCHEMA IF EXISTS dw CASCADE;
CREATE SCHEMA IF NOT EXISTS dw;
"""

CREATE_DIM_TIME = """
CREATE TABLE IF NOT EXISTS dw.dim_time (
    tahun_id SERIAL PRIMARY KEY,
    tahun INTEGER UNIQUE NOT NULL
);
"""

INSERT_DIM_TIME = """
INSERT INTO dw.dim_time (tahun) 
VALUES (2020), (2021), (2022), (2023), (2024), (2025)
ON CONFLICT (tahun) DO NOTHING;
"""

CREATE_DIM_PROVINSI = """
CREATE TABLE IF NOT EXISTS dw.dim_provinsi (
    provinsi_id SERIAL PRIMARY KEY,
    provinsi_name VARCHAR(255) UNIQUE NOT NULL
);
"""

INSERT_DIM_PROVINSI = """
INSERT INTO dw.dim_provinsi (provinsi_name) VALUES
('ACEH'), ('SUMATERA UTARA'), ('SUMATERA BARAT'), ('RIAU'), ('JAMBI'),
('SUMATERA SELATAN'), ('BENGKULU'), ('LAMPUNG'), ('KEP. BANGKA BELITUNG'), 
('KEP. RIAU'), ('DKI JAKARTA'), ('JAWA BARAT'),
('JAWA TENGAH'), ('DI YOGYAKARTA'), ('JAWA TIMUR'), ('BANTEN'), ('BALI'),
('NUSA TENGGARA BARAT'), ('NUSA TENGGARA TIMUR'), ('KALIMANTAN BARAT'),
('KALIMANTAN TENGAH'), ('KALIMANTAN SELATAN'), ('KALIMANTAN TIMUR'),
('KALIMANTAN UTARA'), ('SULAWESI UTARA'), ('SULAWESI TENGAH'),
('SULAWESI SELATAN'), ('SULAWESI TENGGARA'), ('GORONTALO'), ('SULAWESI BARAT'),
('MALUKU'), ('MALUKU UTARA'), ('PAPUA BARAT'), ('PAPUA'), ('INDONESIA')
ON CONFLICT (provinsi_name) DO NOTHING;
"""

CREATE_DIM_INDIKATOR = """
CREATE TABLE IF NOT EXISTS dw.dim_indikator (
    indikator_id SERIAL PRIMARY KEY,
    indikator_name VARCHAR(255) UNIQUE NOT NULL,
    kategori VARCHAR(255),
    satuan VARCHAR(100)
);
"""

INSERT_DIM_INDIKATOR = """
INSERT INTO dw.dim_indikator (indikator_name, kategori, satuan) VALUES
('Persentase_Penduduk_Miskin', 'Ekonomi', 'Persen'),
('Upah_Rata_Rata', 'Ekonomi', 'Rupiah/Jam'),
('AHH', 'Kesehatan', 'Tahun'),
('Unmet_Layanan_Kesehatan', 'Kesehatan', 'Persen'),
('Tenaga_Kerja_Formal', 'Ketenagakerjaan', 'Persen'),
('Lapangan_Kerja_Informal', 'Ketenagakerjaan', 'Persen'),
('APK_Perguruan_Tinggi', 'Pendidikan', 'Persen'),
('APM', 'Pendidikan', 'Persen'),
('Rata_Rata_Lama_Sekolah', 'Pendidikan', 'Tahun'),
('Memiliki_Telepon_Seluler', 'Teknologi', 'Persen'),
('Mengakses_Internet', 'Teknologi', 'Persen')
ON CONFLICT (indikator_name) DO NOTHING;
"""

CREATE_DIM_INDIKATOR_DIMENSI = """
CREATE TABLE IF NOT EXISTS dw.dim_indikator_dimensi (
    indikator_dimensi_id SERIAL PRIMARY KEY,
    indikator_id INTEGER NOT NULL REFERENCES dw.dim_indikator(indikator_id) ON DELETE CASCADE,
    dimensi_name VARCHAR(255) NOT NULL,
    dimensi_description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(indikator_id, dimensi_name)
);
CREATE INDEX IF NOT EXISTS idx_ind_dim_indikator ON dw.dim_indikator_dimensi(indikator_id);
CREATE INDEX IF NOT EXISTS idx_ind_dim_dimensi ON dw.dim_indikator_dimensi(dimensi_name);
"""

INSERT_DIM_INDIKATOR_DIMENSI = """
INSERT INTO dw.dim_indikator_dimensi (indikator_id, dimensi_name, dimensi_description) 
-- APM with 3 education levels
SELECT di.indikator_id, 'APM-SD', 'Angka Partisipasi Murni SD/sederajat'
FROM dw.dim_indikator di WHERE di.indikator_name = 'APM'
UNION ALL
SELECT di.indikator_id, 'APM-SMP', 'Angka Partisipasi Murni SMP/sederajat'
FROM dw.dim_indikator di WHERE di.indikator_name = 'APM'
UNION ALL
SELECT di.indikator_id, 'APM-SM', 'Angka Partisipasi Murni SM/sederajat'
FROM dw.dim_indikator di WHERE di.indikator_name = 'APM'
-- AHH with gender split
UNION ALL
SELECT di.indikator_id, 'Laki-laki', 'Laki-laki'
FROM dw.dim_indikator di WHERE di.indikator_name = 'AHH'
UNION ALL
SELECT di.indikator_id, 'Perempuan', 'Perempuan'
FROM dw.dim_indikator di WHERE di.indikator_name = 'AHH'
-- Teknologi with urban/rural split
UNION ALL
SELECT di.indikator_id, 'Perkotaan+Perdesaan', 'Perkotaan dan Perdesaan'
FROM dw.dim_indikator di WHERE di.indikator_name = 'Memiliki_Telepon_Seluler'
UNION ALL
SELECT di.indikator_id, 'Perkotaan+Perdesaan', 'Perkotaan dan Perdesaan'
FROM dw.dim_indikator di WHERE di.indikator_name = 'Mengakses_Internet'
-- Default/overall dimensions for indicators without sub-dimensions
UNION ALL
SELECT di.indikator_id, 'Total', 'Overall/Aggregate'
FROM dw.dim_indikator di WHERE di.indikator_name IN (
    'Persentase_Penduduk_Miskin',
    'Upah_Rata_Rata',
    'Unmet_Layanan_Kesehatan',
    'Tenaga_Kerja_Formal',
    'Lapangan_Kerja_Informal',
    'APK_Perguruan_Tinggi',
    'Rata_Rata_Lama_Sekolah'
)
ON CONFLICT (indikator_id, dimensi_name) DO NOTHING;
"""

CREATE_FACT_TABLE = """
CREATE TABLE IF NOT EXISTS dw.fact_indikator (
    fact_id SERIAL PRIMARY KEY,
    tahun_id INTEGER NOT NULL REFERENCES dw.dim_time(tahun_id),
    provinsi_id INTEGER NOT NULL REFERENCES dw.dim_provinsi(provinsi_id),
    indikator_dimensi_id INTEGER REFERENCES dw.dim_indikator_dimensi(indikator_dimensi_id),
    nilai NUMERIC(15, 4),
    data_quality_flag VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_fact_tahun ON dw.fact_indikator(tahun_id);
CREATE INDEX IF NOT EXISTS idx_fact_provinsi ON dw.fact_indikator(provinsi_id);
CREATE INDEX IF NOT EXISTS idx_fact_indikator_dimensi ON dw.fact_indikator(indikator_dimensi_id);
CREATE INDEX IF NOT EXISTS idx_fact_composite ON dw.fact_indikator(tahun_id, provinsi_id, indikator_dimensi_id);
"""


def execute_ddl(engine, ddl_statement, description=""):
    """Execute DDL statement"""
    try:
        with engine.connect() as conn:
            conn.execute(text(ddl_statement))
            conn.commit()
        if description:
            logger.info(f"[OK] {description}")
        return True
    except SQLAlchemyError as e:
        if "already exists" not in str(e).lower():
            logger.error(f"[FAIL] {description}: {str(e)}")
            return False
        return True  # Table already exists, that's okay
    except Exception as e:
        logger.error(f"[FAIL] {description}: {str(e)}")
        return False


def load_to_staging(clean_df):
    """
    Load clean DataFrame to staging.indikator_raw table using pure Python.
    
    Args:
        clean_df (pd.DataFrame): Cleaned DataFrame from transformer
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Starting load to staging phase (Python-based)...")
    
    try:
        engine = create_engine(PSQL_CONNECTION_STRING)
        
        # Create schema
        if not execute_ddl(engine, CREATE_STAGING_SCHEMA, "Create staging schema"):
            logger.error("[FAIL] Failed to create staging schema")
            return False
        
        # Create staging table
        if not execute_ddl(engine, CREATE_STAGING_TABLE, "Create indikator_raw table"):
            logger.error("[FAIL] Failed to create staging table")
            return False
        
        # Create validation table
        if not execute_ddl(engine, CREATE_VALIDATION_TABLE, "Create validation_report table"):
            logger.error("[FAIL] Failed to create validation table")
            return False
        
        # Insert data
        logger.info(f"Inserting {len(clean_df)} rows into staging table...")
        clean_df.to_sql(
            'indikator_raw',
            engine,
            schema='staging',
            if_exists='append',
            index=False,
            method='multi',
            chunksize=1000
        )
        logger.info(f"[OK] Inserted {len(clean_df)} rows into staging table")
        
        # Verify
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM staging.indikator_raw"))
            row_count = result.scalar()
        
        logger.info(f"[OK] Staging load complete: {row_count} rows in table")
        engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Error during staging load: {str(e)}")
        return False


def create_dw_schema():
    """
    Create data warehouse schema and dimension tables using pure Python.
    
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Starting DW schema creation (Python-based)...")
    
    try:
        engine = create_engine(PSQL_CONNECTION_STRING)
        
        # Create schema
        if not execute_ddl(engine, CREATE_DW_SCHEMA, "Create dw schema"):
            logger.error("[FAIL] Failed to create dw schema")
            return False
        
        # Create dimension tables
        if not execute_ddl(engine, CREATE_DIM_TIME, "Create dim_time table"):
            return False
        
        if not execute_ddl(engine, INSERT_DIM_TIME, "Insert time dimension data"):
            return False
        
        if not execute_ddl(engine, CREATE_DIM_PROVINSI, "Create dim_provinsi table"):
            return False
        
        if not execute_ddl(engine, INSERT_DIM_PROVINSI, "Insert provinsi dimension data"):
            return False
        
        if not execute_ddl(engine, CREATE_DIM_INDIKATOR, "Create dim_indikator table"):
            return False
        
        if not execute_ddl(engine, INSERT_DIM_INDIKATOR, "Insert indikator dimension data"):
            return False
        
        # Create sub-dimension table for indicator dimensions
        if not execute_ddl(engine, CREATE_DIM_INDIKATOR_DIMENSI, "Create dim_indikator_dimensi table"):
            return False
        
        if not execute_ddl(engine, INSERT_DIM_INDIKATOR_DIMENSI, "Insert indikator_dimensi dimension data"):
            return False
        
        # Create fact table
        if not execute_ddl(engine, CREATE_FACT_TABLE, "Create fact_indikator table"):
            return False
        
        logger.info("[OK] DW schema creation complete")
        engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Error during DW schema creation: {str(e)}")
        return False


def load_to_dw(clean_df):
    """
    Load data to DW fact table using pure Python.
    
    Args:
        clean_df (pd.DataFrame): Cleaned DataFrame from transformer
        
    Returns:
        bool: True if successful, False otherwise
    """
    logger.info("Starting DW load phase (Python-based)...")
    
    try:
        engine = create_engine(PSQL_CONNECTION_STRING)
        
        # Prepare fact data
        logger.info("Preparing fact table data...")
        fact_data = []
        skipped_count = 0
        
        for _, row in clean_df.iterrows():
            # Get IDs from dimensions
            with engine.connect() as conn:
                # Get tahun_id
                tahun_result = conn.execute(
                    text("SELECT tahun_id FROM dw.dim_time WHERE tahun = :tahun"),
                    {"tahun": row['tahun']}
                )
                tahun_id = tahun_result.scalar()
                
                # Get provinsi_id
                prov_result = conn.execute(
                    text("SELECT provinsi_id FROM dw.dim_provinsi WHERE provinsi_name = :name"),
                    {"name": row['provinsi']}
                )
                provinsi_id = prov_result.scalar()
                
                # Get indikator_dimensi_id
                # Match on indicator name and dimensi
                dimensi_val = row.get('dimensi')
                if pd.notna(dimensi_val) and str(dimensi_val).strip() not in ('None', ''):
                    # Use specific dimension
                    ind_dim_result = conn.execute(
                        text("""
                            SELECT id.indikator_dimensi_id 
                            FROM dw.dim_indikator_dimensi id
                            JOIN dw.dim_indikator di ON id.indikator_id = di.indikator_id
                            WHERE di.indikator_name = :ind_name AND id.dimensi_name = :dim_name
                        """),
                        {"ind_name": row['indikator'], "dim_name": str(dimensi_val).strip()}
                    )
                else:
                    # Use default 'Total' dimension
                    ind_dim_result = conn.execute(
                        text("""
                            SELECT id.indikator_dimensi_id 
                            FROM dw.dim_indikator_dimensi id
                            JOIN dw.dim_indikator di ON id.indikator_id = di.indikator_id
                            WHERE di.indikator_name = :ind_name AND id.dimensi_name = 'Total'
                        """),
                        {"ind_name": row['indikator']}
                    )
                
                indikator_dimensi_id = ind_dim_result.scalar() if ind_dim_result else None
                
                if tahun_id and provinsi_id and indikator_dimensi_id:
                    fact_data.append({
                        'tahun_id': tahun_id,
                        'provinsi_id': provinsi_id,
                        'indikator_dimensi_id': indikator_dimensi_id,
                        'nilai': row['nilai'],
                        'data_quality_flag': row['data_kualitas_flag']
                    })
                elif tahun_id and provinsi_id:
                    skipped_count += 1
        
        if fact_data:
            fact_df = pd.DataFrame(fact_data)
            logger.info(f"Inserting {len(fact_df)} fact records...")
            
            fact_df.to_sql(
                'fact_indikator',
                engine,
                schema='dw',
                if_exists='append',
                index=False,
                method='multi',
                chunksize=1000
            )
            
            logger.info(f"[OK] Inserted {len(fact_df)} fact records")
        
        if skipped_count > 0:
            logger.warning(f"[WARN] Skipped {skipped_count} records with missing dimension mappings")
        
        # Verify
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM dw.fact_indikator"))
            fact_count = result.scalar()
        
        logger.info(f"[OK] DW load complete: {fact_count} rows in fact table")
        engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"[FAIL] Error during DW load: {str(e)}")
        import traceback
        traceback.print_exc()
        return False
