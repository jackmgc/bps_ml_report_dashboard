"""Extractor module - reads and cleans CSV files using table-specific cleaners"""
import os
import pandas as pd
from config.db_config import DATA_FOLDER
from config.constants import CSV_FILES
from etl.table_cleaners import get_cleaner
from utils.logger import get_logger

logger = get_logger(__name__)

def extract_all_csvs(data_folder=None):
    """
    Extract and clean all CSV files from data folder using table-specific cleaners.
    
    Each CSV file has a unique structure, so we apply specialized cleaning logic:
    - APM: Splits 3 education levels (SD/SMP/SM)
    - AHH: Splits 2 genders (Laki-laki/Perempuan)
    - Poverty: Handles special year range (2021-2025)
    - Others: Standard unpivot from wide to long format
    
    Args:
        data_folder (str): Path to data folder. If None, uses DATA_FOLDER from config.
        
    Returns:
        dict: Dictionary mapping CSV filename -> Cleaned DataFrame (long format)
        
    Raises:
        FileNotFoundError: If CSV file is not found
        ValueError: If no cleaner registered for CSV file
    """
    if data_folder is None:
        data_folder = DATA_FOLDER
    
    logger.info(f"Starting extraction & cleaning phase from folder: {data_folder}")
    
    cleaned_dataframes = {}
    
    for csv_file in CSV_FILES:
        csv_path = os.path.join(data_folder, csv_file)
        
        if not os.path.exists(csv_path):
            logger.error(f"CSV file not found: {csv_path}")
            raise FileNotFoundError(f"CSV file not found: {csv_path}")
        
        try:
            # Get the appropriate cleaner for this CSV
            cleaner_config = get_cleaner(csv_file)
            cleaner_func = cleaner_config['function']
            
            # Call cleaner function
            if cleaner_config['cleaner'] == 'simple':
                # Simple cleaners need parameters
                params = cleaner_config['params']
                df = cleaner_func(csv_path, **params)
            else:
                # Custom cleaners take only filepath
                df = cleaner_func(csv_path)
            
            logger.info(f"[OK] Cleaned: {csv_file} ({len(df)} rows)")
            cleaned_dataframes[csv_file] = df
            
        except Exception as e:
            logger.error(f"Error cleaning CSV {csv_file}: {str(e)}")
            raise
    
    logger.info(f"[OK] Extraction & cleaning complete: {len(cleaned_dataframes)} files cleaned")
    return cleaned_dataframes


def get_csv_columns(df):
    """
    Get column information from extracted DataFrame.
    
    Args:
        df (pd.DataFrame): DataFrame to analyze
        
    Returns:
        dict: Column information
    """
    return {
        "total_columns": len(df.columns),
        "column_names": list(df.columns),
        "total_rows": len(df),
    }
