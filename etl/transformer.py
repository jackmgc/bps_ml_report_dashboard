"""Transformer module - validates and flags data quality issues"""
import pandas as pd
import numpy as np
from datetime import datetime
from config.constants import CANONICAL_PROVINCES, NUMERIC_RANGES
from utils.logger import get_logger

logger = get_logger(__name__)

def transform_to_canonical(cleaned_dataframes, skip_validation=False):
    """
    Transform cleaned DataFrames to canonical format with data quality validation.
    
    The extractor already handles structural normalization (unpivoting, splitting dimensions).
    This transformer focuses on:
    - Validating province names against canonical list
    - Validating numeric values against known ranges
    - Flagging data quality issues
    - Adding standardized metadata columns
    
    Args:
        cleaned_dataframes (dict): Dict mapping CSV filename -> Cleaned DataFrame
        skip_validation (bool): If True, skip validation checks
        
    Returns:
        pd.DataFrame: Canonical format with columns:
            [provinsi, tahun, kategori, indikator, dimensi, nilai, satuan, 
             is_national_aggregate, sumber, data_kualitas_flag, catatan, created_at]
    """
    logger.info("Starting transformation phase")
    logger.info(f"Processing {len(cleaned_dataframes)} cleaned DataFrames")
    
    all_transformed = []
    
    for csv_file, df in cleaned_dataframes.items():
        logger.info(f"Transforming {csv_file}")
        
        # Ensure required columns exist
        required_cols = ['provinsi', 'tahun', 'kategori', 'indikator', 'nilai', 'satuan', 'sumber']
        if not all(col in df.columns for col in required_cols):
            logger.error(f"Missing required columns in {csv_file}")
            raise ValueError(f"Missing required columns in {csv_file}")
        
        # Make a copy to avoid modifying original
        df_copy = df.copy()
        
        # Fill missing dimensi with None
        if 'dimensi' not in df_copy.columns:
            df_copy['dimensi'] = None
        
        # Fill missing columns with defaults
        if 'is_national_aggregate' not in df_copy.columns:
            df_copy['is_national_aggregate'] = False
        
        # Validate and flag data quality
        if not skip_validation:
            df_copy = validate_data_quality(df_copy, csv_file)
        else:
            # Still need to initialize quality columns
            df_copy['data_kualitas_flag'] = 'VALID'
            df_copy['catatan'] = None
        
        all_transformed.append(df_copy)
        logger.debug(f"{csv_file}: {len(df_copy)} rows after validation")
    
    # Combine all transformed data
    canonical_df = pd.concat(all_transformed, ignore_index=True)
    
    # Ensure column order
    column_order = [
        'provinsi', 'tahun', 'kategori', 'indikator', 'dimensi', 'nilai', 'satuan',
        'is_national_aggregate', 'sumber', 'data_kualitas_flag', 'catatan', 'created_at'
    ]
    
    canonical_df = canonical_df[column_order]
    
    logger.info(f"[OK] Transformation complete: {len(canonical_df)} total rows")
    logger.info(f"Data quality summary:")
    quality_summary = canonical_df['data_kualitas_flag'].value_counts()
    for flag, count in quality_summary.items():
        logger.info(f"  {flag}: {count}")
    
    return canonical_df


def validate_data_quality(df, csv_file):
    """
    Validate and flag data quality issues for each row.
    
    Validation checks:
    1. Province name: Must be in CANONICAL_PROVINCES
    2. Numeric value: Must be numeric and not NaN
    3. Range check: Value within expected range for indicator category
    4. Year check: Must be in expected range
    
    Flags:
    - None (NULL): Valid data
    - 'VALID': Data passes all checks
    - 'OUTLIER': Value outside normal range for category
    - 'MISSING_DATA': Invalid province, NaN value, or missing year
    - 'INCONSISTENT': Cross-metric inconsistency (employment formal+informal not ~100%)
    
    Args:
        df (pd.DataFrame): DataFrame with columns [provinsi, tahun, kategori, indikator, nilai, ...]
        csv_file (str): Name of source CSV file for logging
        
    Returns:
        pd.DataFrame: DataFrame with added/updated columns:
            - data_kualitas_flag (str): Quality flag
            - catatan (str): Explanation of any issues
    """
    logger.debug(f"Validating data quality for {csv_file}")
    
    # Initialize quality columns
    df['data_kualitas_flag'] = None
    df['catatan'] = None
    
    # Convert nilai to numeric (coerce errors to NaN)
    df['nilai'] = pd.to_numeric(df['nilai'], errors='coerce')
    
    # Check 1: Province validation
    invalid_provinces = ~df['provinsi'].isin(CANONICAL_PROVINCES)
    df.loc[invalid_provinces, 'data_kualitas_flag'] = 'MISSING_DATA'
    df.loc[invalid_provinces, 'catatan'] = df.loc[invalid_provinces, 'provinsi'].apply(
        lambda x: f'Invalid province: {x}'
    )
    
    # Check 2: Missing values
    missing_values = df['nilai'].isna()
    df.loc[missing_values & (df['data_kualitas_flag'].isna()), 'data_kualitas_flag'] = 'MISSING_DATA'
    df.loc[missing_values & (df['catatan'].isna()), 'catatan'] = 'Missing value'
    
    # Check 3: Year validation (2020-2025 expected, but 2021-2025 for poverty)
    invalid_years = ~df['tahun'].isin(range(2020, 2026))
    df.loc[invalid_years & (df['data_kualitas_flag'].isna()), 'data_kualitas_flag'] = 'MISSING_DATA'
    df.loc[invalid_years & (df['catatan'].isna()), 'catatan'] = df.loc[invalid_years, 'tahun'].apply(
        lambda x: f'Invalid year: {x}'
    )
    
    # Check 4: Range validation by category
    df = validate_numeric_ranges(df)
    
    # Check 5: Cross-metric consistency
    df = check_employment_consistency(df)
    
    # Set to VALID if no other flag
    df.loc[df['data_kualitas_flag'].isna(), 'data_kualitas_flag'] = 'VALID'
    
    return df


def validate_numeric_ranges(df):
    """
    Validate numeric values against expected ranges by category/indicator.
    
    Expected ranges:
    - Persen: 0-100 (percentages)
    - Tahun: 50-85 (life expectancy, education years)
    - Rupiah/Jam: 10,000-50,000 (wages)
    
    Args:
        df (pd.DataFrame): DataFrame with 'satuan' and 'nilai' columns
        
    Returns:
        pd.DataFrame: Updated DataFrame with OUTLIER flags where applicable
    """
    # Percentage checks (0-100)
    persen_rows = (df['satuan'] == 'Persen') & (df['data_kualitas_flag'].isna())
    out_of_range = ((df.loc[persen_rows, 'nilai'] < 0) | (df.loc[persen_rows, 'nilai'] > 100))
    df.loc[persen_rows & out_of_range, 'data_kualitas_flag'] = 'OUTLIER'
    df.loc[persen_rows & out_of_range, 'catatan'] = 'Value outside 0-100 range for percentage'
    
    # Year range checks (50-85 for life expectancy, education duration)
    tahun_rows = (df['satuan'] == 'Tahun') & (df['data_kualitas_flag'].isna())
    out_of_range = ((df.loc[tahun_rows, 'nilai'] < 50) | (df.loc[tahun_rows, 'nilai'] > 85))
    df.loc[tahun_rows & out_of_range, 'data_kualitas_flag'] = 'OUTLIER'
    df.loc[tahun_rows & out_of_range, 'catatan'] = 'Value outside 50-85 range'
    
    # Wage checks (might be local minimum to reasonable max)
    # Rupiah/Jam: 10,000-50,000
    rupiah_rows = (df['satuan'].str.contains('Rupiah', na=False)) & (df['data_kualitas_flag'].isna())
    out_of_range = ((df.loc[rupiah_rows, 'nilai'] < 10000) | (df.loc[rupiah_rows, 'nilai'] > 50000))
    df.loc[rupiah_rows & out_of_range, 'data_kualitas_flag'] = 'OUTLIER'
    df.loc[rupiah_rows & out_of_range, 'catatan'] = 'Wage value outside 10,000-50,000 range'
    
    return df


def check_employment_consistency(df):
    """
    Check cross-metric consistency for employment indicators.
    
    Rule: Formal employment + Informal employment should approximately equal 100%
    (accounting for self-employed and unemployed, tolerance ±10%)
    
    Args:
        df (pd.DataFrame): DataFrame with indikator column
        
    Returns:
        pd.DataFrame: Updated with INCONSISTENT flags
    """
    # This check requires data from both formal and informal employment
    # For now, we'll implement it as a post-load validation
    # (easier to do after all data is in the database)
    
    return df
