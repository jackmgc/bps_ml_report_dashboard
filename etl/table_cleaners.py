"""Table-specific cleaners for handling CSV files with complex formats"""
import pandas as pd
import numpy as np
from datetime import datetime
from config.constants import CANONICAL_PROVINCES, DROPPED_PROVINCES, NON_PROVINCE_ROWS
from utils.logger import get_logger

logger = get_logger(__name__)


def _filter_provinces(df, csv_file):
    """
    Filter DataFrame to keep only canonical provinces.
    
    Logs which provinces were dropped and why.
    Sets is_national_aggregate=True for INDONESIA rows.
    
    Args:
        df (pd.DataFrame): DataFrame with 'provinsi' column
        csv_file (str): Source filename for logging
        
    Returns:
        pd.DataFrame: Filtered DataFrame
    """
    all_provinces = df['provinsi'].unique()
    
    # Identify dropped provinces (new PAPUA provinces with incomplete data)
    dropped = [p for p in all_provinces if p in DROPPED_PROVINCES]
    if dropped:
        logger.info(f"  [{csv_file}] Dropping {len(dropped)} incomplete PAPUA provinces: {dropped}")
    
    # Identify unknown/footer rows being filtered out
    unknown = [
        p for p in all_provinces 
        if p not in CANONICAL_PROVINCES 
        and p not in DROPPED_PROVINCES
        and pd.notna(p)
        and str(p).strip() not in NON_PROVINCE_ROWS
    ]
    if unknown:
        logger.warning(f"  [{csv_file}] Unknown provinces filtered out: {unknown}")
    
    # Filter to canonical only
    df = df[df['provinsi'].isin(CANONICAL_PROVINCES)].copy()
    
    # Mark national aggregate
    df['is_national_aggregate'] = df['provinsi'] == 'INDONESIA'
    
    kept_count = df['provinsi'].nunique()
    logger.info(f"  [{csv_file}] Kept {kept_count} canonical provinces (incl. INDONESIA aggregate)")
    
    return df


def _read_all_province_rows(raw_df, data_start_idx, num_data_cols):
    """
    Read ALL data rows from a CSV (not trimmed by province count).
    
    Returns province names and data block as separate arrays,
    keeping them aligned row-by-row even when lengths differ.
    
    Args:
        raw_df: Raw DataFrame from pd.read_csv(header=None)
        data_start_idx: Row index where data starts
        num_data_cols: Number of data columns to extract (e.g. 5 for 5 years)
        
    Returns:
        tuple: (provinces_array, data_df) both with same number of rows
    """
    # Get ALL rows from data_start_idx to end
    all_col0 = raw_df.iloc[data_start_idx:, 0].values
    all_data = raw_df.iloc[data_start_idx:, 1:1+num_data_cols].copy()
    all_data = all_data.reset_index(drop=True)
    
    # Filter out rows where column 0 is NaN or is a footer row
    valid_mask = []
    provinces = []
    for val in all_col0:
        if pd.isna(val):
            valid_mask.append(False)
            provinces.append(None)
        else:
            sval = str(val).strip()
            if sval in NON_PROVINCE_ROWS or sval == '':
                valid_mask.append(False)
            else:
                valid_mask.append(True)
            provinces.append(sval)
    
    valid_mask = pd.Series(valid_mask)
    provinces = pd.Series(provinces)
    
    # Keep only valid rows
    filtered_data = all_data[valid_mask.values].reset_index(drop=True)
    filtered_provinces = provinces[valid_mask.values].reset_index(drop=True).values
    
    return filtered_provinces, filtered_data


# =============================================================================
# CLEANER 1: APM (Angka Partisipasi Murni) - 3 Education Levels
# =============================================================================
def clean_apm(filepath):
    """
    Clean APM table with 3 education level sub-indicators (SD/SMP/SM).
    
    Structure:
    - Row 0: Title
    - Row 1: Categories (SD/sederajat | SMP/sederajat | SM/sederajat)
    - Row 2: Years (2020-2024 repeated 3 times)
    - Data rows: 38+ provinces + INDONESIA + footer
    
    Returns: DataFrame with columns [provinsi, tahun, indikator, dimensi, nilai]
    Expected: 37 canonical provinces × 3 levels × 5 years = 555 rows
    """
    logger.info(f"Cleaning APM table from {filepath}")
    
    # Read raw data without header processing
    raw_df = pd.read_csv(filepath, header=None, skiprows=0)
    
    # Extract years from row 2
    year_row = raw_df.iloc[2, 1:].values
    years = [int(y) for y in year_row[:5]]  # First 5 are years
    logger.info(f"Detected years: {years}")
    
    # Get ALL province names from column 0 (row 3 onwards), including INDONESIA & footer
    all_col0 = raw_df.iloc[3:, 0].values
    
    # Build valid province mask (exclude NaN and footer rows)
    valid_mask = []
    province_names = []
    for val in all_col0:
        if pd.isna(val):
            valid_mask.append(False)
            province_names.append(None)
        else:
            sval = str(val).strip()
            if sval in NON_PROVINCE_ROWS or sval == '':
                valid_mask.append(False)
            else:
                valid_mask.append(True)
            province_names.append(sval)
    
    valid_mask = pd.Series(valid_mask)
    province_names = pd.Series(province_names)
    
    logger.info(f"Found {valid_mask.sum()} province rows (before canonical filtering)")
    
    # Define the 3 education level blocks (each has 5 year columns)
    education_levels = ['APM-SD', 'APM-SMP', 'APM-SM']
    block_starts = [1, 6, 11]  # Column indices where each block starts
    
    all_rows = []
    
    for block_idx, (block_start, education) in enumerate(zip(block_starts, education_levels)):
        logger.info(f"Processing {education} block (columns {block_start}-{block_start+4})")
        
        # Extract data for this education level - ALL rows
        block_data = raw_df.iloc[3:, block_start:block_start+5].copy()
        block_data.columns = years
        block_data = block_data.reset_index(drop=True)
        
        # Apply valid mask and attach province names
        block_data_filtered = block_data[valid_mask.values].reset_index(drop=True)
        block_provinces = province_names[valid_mask.values].reset_index(drop=True).values
        block_data_filtered['provinsi'] = block_provinces
        
        # Unpivot to long format
        melted = pd.melt(
            block_data_filtered,
            id_vars=['provinsi'],
            var_name='tahun',
            value_name='nilai'
        )
        
        # Add metadata columns
        melted['indikator'] = 'APM'
        melted['dimensi'] = education
        melted['kategori'] = 'Pendidikan'
        melted['satuan'] = 'Persen'
        melted['sumber'] = 'BPS'
        melted['is_national_aggregate'] = False
        melted['created_at'] = datetime.now().isoformat()
        
        # Convert value to numeric
        melted['nilai'] = pd.to_numeric(melted['nilai'], errors='coerce')
        
        all_rows.append(melted)
        logger.debug(f"{education}: {len(melted)} rows extracted")
    
    result = pd.concat(all_rows, ignore_index=True)
    
    # Filter to canonical provinces and mark INDONESIA
    result = _filter_provinces(result, 'APM')
    
    logger.info(f"APM cleaning complete: {len(result)} rows")
    
    return result[['provinsi', 'tahun', 'kategori', 'indikator', 'dimensi', 'nilai', 
                   'satuan', 'is_national_aggregate', 'sumber', 'created_at']]


# =============================================================================
# CLEANER 2: AHH (Angka Harapan Hidup) - Gender Split
# =============================================================================
def clean_ahh(filepath):
    """
    Clean AHH table with gender split (Laki-laki | Perempuan).
    
    Structure:
    - Row 0: Title
    - Row 1: Genders (Laki-laki | Perempuan)
    - Row 2: Years (2020-2024 repeated 2 times)
    - Data rows: 38+ provinces + INDONESIA + footer
    
    Returns: DataFrame with columns [provinsi, tahun, indikator, dimensi, nilai]
    Expected: 37 canonical provinces × 2 genders × 5 years = 370 rows
    """
    logger.info(f"Cleaning AHH table from {filepath}")
    
    # Read raw data
    raw_df = pd.read_csv(filepath, header=None, skiprows=0)
    
    # Extract years
    year_row = raw_df.iloc[2, 1:].values
    years = [int(y) for y in year_row[:5]]  # First 5 are years
    logger.info(f"Detected years: {years}")
    
    # Get ALL province names from column 0 (row 3 onwards)
    all_col0 = raw_df.iloc[3:, 0].values
    valid_mask = []
    province_names = []
    for val in all_col0:
        if pd.isna(val):
            valid_mask.append(False)
            province_names.append(None)
        else:
            sval = str(val).strip()
            if sval in NON_PROVINCE_ROWS or sval == '':
                valid_mask.append(False)
            else:
                valid_mask.append(True)
            province_names.append(sval)
    
    valid_mask = pd.Series(valid_mask)
    province_names = pd.Series(province_names)
    
    logger.info(f"Found {valid_mask.sum()} province rows (before canonical filtering)")
    
    # Define gender blocks
    genders = ['Laki-laki', 'Perempuan']
    block_starts = [1, 6]  # Column indices
    
    all_rows = []
    
    for block_idx, (block_start, gender) in enumerate(zip(block_starts, genders)):
        logger.info(f"Processing {gender} block (columns {block_start}-{block_start+4})")
        
        # Extract data for this gender - ALL rows
        block_data = raw_df.iloc[3:, block_start:block_start+5].copy()
        block_data.columns = years
        block_data = block_data.reset_index(drop=True)
        
        # Apply valid mask and attach province names
        block_data_filtered = block_data[valid_mask.values].reset_index(drop=True)
        block_provinces = province_names[valid_mask.values].reset_index(drop=True).values
        block_data_filtered['provinsi'] = block_provinces
        
        # Unpivot to long format
        melted = pd.melt(
            block_data_filtered,
            id_vars=['provinsi'],
            var_name='tahun',
            value_name='nilai'
        )
        
        # Add metadata columns
        melted['indikator'] = 'AHH'
        melted['dimensi'] = gender
        melted['kategori'] = 'Kesehatan'
        melted['satuan'] = 'Tahun'
        melted['sumber'] = 'BPS'
        melted['is_national_aggregate'] = False
        melted['created_at'] = datetime.now().isoformat()
        
        # Convert value to numeric
        melted['nilai'] = pd.to_numeric(melted['nilai'], errors='coerce')
        
        all_rows.append(melted)
        logger.debug(f"{gender}: {len(melted)} rows extracted")
    
    result = pd.concat(all_rows, ignore_index=True)
    
    # Filter to canonical provinces and mark INDONESIA
    result = _filter_provinces(result, 'AHH')
    
    logger.info(f"AHH cleaning complete: {len(result)} rows")
    
    return result[['provinsi', 'tahun', 'kategori', 'indikator', 'dimensi', 'nilai', 
                   'satuan', 'is_national_aggregate', 'sumber', 'created_at']]


# =============================================================================
# CLEANER 3: Poverty (Persentase Penduduk Miskin) - Special Year Range
# =============================================================================
def clean_poverty(filepath):
    """
    Clean poverty table with unusual year range (2021-2025 instead of 2020-2024).
    
    Structure:
    - Row 0: Title
    - Row 1: "Jumlah" (total category)
    - Row 2: Years 2021-2025 (5 columns)
    - Row 3: "Semester 1 (Maret)" (metadata - skip)
    - Data rows: 38+ provinces + INDONESIA + footer
    
    Returns: DataFrame with columns [provinsi, tahun, indikator, dimensi, nilai]
    Expected: 37 canonical provinces × 1 × 5 years = 185 rows
    """
    logger.info(f"Cleaning Poverty table from {filepath}")
    
    # Read raw data
    raw_df = pd.read_csv(filepath, header=None, skiprows=0)
    
    # Extract years from row 2 (special: 2021-2025)
    year_row = raw_df.iloc[2, 1:].values
    years = [int(y) for y in year_row[:5]]
    logger.info(f"Detected years: {years}")
    
    # Extract ALL province names and data (row 4 onwards — extra metadata row 3)
    provinces, data_df = _read_all_province_rows(raw_df, data_start_idx=4, num_data_cols=5)
    logger.info(f"Found {len(provinces)} province rows (before canonical filtering)")
    
    data_df.columns = years
    data_df['provinsi'] = provinces
    
    # Unpivot to long format
    melted = pd.melt(
        data_df,
        id_vars=['provinsi'],
        var_name='tahun',
        value_name='nilai'
    )
    
    # Add metadata columns
    melted['indikator'] = 'Persentase_Penduduk_Miskin'
    melted['dimensi'] = None  # No dimension split for this indicator
    melted['kategori'] = 'Ekonomi'
    melted['satuan'] = 'Persen'
    melted['sumber'] = 'BPS'
    melted['is_national_aggregate'] = False
    melted['created_at'] = datetime.now().isoformat()
    
    # Convert value to numeric
    melted['nilai'] = pd.to_numeric(melted['nilai'], errors='coerce')
    
    # Filter to canonical provinces and mark INDONESIA
    melted = _filter_provinces(melted, 'Poverty')
    
    logger.info(f"[OK] Poverty cleaning complete: {len(melted)} rows")
    
    return melted[['provinsi', 'tahun', 'kategori', 'indikator', 'dimensi', 'nilai', 
                   'satuan', 'is_national_aggregate', 'sumber', 'created_at']]


# =============================================================================
# CLEANER 4: Simple Tables (Generic Handler)
# =============================================================================
def clean_simple(filepath, indicator_name, category, dimension, satuan, years_range=(2020, 2024)):
    """
    Generic cleaner for simple tables with single indicator and year columns.
    
    Structure:
    - Row 0: Title
    - Row 1: Optional category (e.g., "Perkotaan+Perdesaan") - skipped
    - Row 1 or 2: Years (2020-2024 by default, or custom range)
    - Data rows: 38+ provinces + INDONESIA + footer
    
    Args:
        filepath: Path to CSV file
        indicator_name: Name of indicator (e.g., 'Upah_Rata_Rata')
        category: Category name (e.g., 'Ekonomi')
        dimension: Dimension name (None or specific value)
        satuan: Unit (e.g., 'Rupiah/Jam', 'Persen', 'Tahun')
        years_range: Tuple (start_year, end_year) default 2020-2024
    
    Returns: Normalized DataFrame
    """
    logger.info(f"Cleaning {indicator_name} table from {filepath}")
    
    # Read raw data
    raw_df = pd.read_csv(filepath, header=None, skiprows=0)
    
    # Detect year row - look for numeric values in row 1 or row 2
    year_row_idx = None
    data_start_idx = None
    
    # Try row 1 (most common)
    year_candidates = raw_df.iloc[1, 1:].fillna('').astype(str)
    if year_candidates.str.isnumeric().sum() >= 4:
        year_row_idx = 1
        data_start_idx = 2
    # Try row 2 (if row 1 is metadata like "Perkotaan+Perdesaan")
    elif raw_df.shape[0] > 2:
        year_candidates = raw_df.iloc[2, 1:].fillna('').astype(str)
        if year_candidates.str.isnumeric().sum() >= 4:
            year_row_idx = 2
            data_start_idx = 3
    
    if year_row_idx is None:
        logger.error(f"Could not detect year row in {filepath}")
        raise ValueError(f"Cannot detect year row in {filepath}")
    
    # Extract years
    year_row = raw_df.iloc[year_row_idx, 1:].values
    years = [int(y) for y in year_row[:5]]  # Take first 5 years
    logger.info(f"Detected years: {years}")
    
    # Extract ALL province names and data (not trimmed)
    provinces, data_df = _read_all_province_rows(raw_df, data_start_idx, num_data_cols=5)
    logger.info(f"Found {len(provinces)} province rows (before canonical filtering)")
    
    data_df.columns = years
    data_df['provinsi'] = provinces
    
    # Unpivot to long format
    melted = pd.melt(
        data_df,
        id_vars=['provinsi'],
        var_name='tahun',
        value_name='nilai'
    )
    
    # Add metadata columns
    melted['indikator'] = indicator_name
    melted['dimensi'] = dimension
    melted['kategori'] = category
    melted['satuan'] = satuan
    melted['sumber'] = 'BPS'
    melted['is_national_aggregate'] = False
    melted['created_at'] = datetime.now().isoformat()
    
    # Convert value to numeric
    melted['nilai'] = pd.to_numeric(melted['nilai'], errors='coerce')
    
    # Filter to canonical provinces and mark INDONESIA
    melted = _filter_provinces(melted, indicator_name)
    
    logger.info(f"{indicator_name} cleaning complete: {len(melted)} rows")
    
    return melted[['provinsi', 'tahun', 'kategori', 'indikator', 'dimensi', 'nilai', 
                   'satuan', 'is_national_aggregate', 'sumber', 'created_at']]


# =============================================================================
# TABLE CLEANER REGISTRY - Maps filename to cleaner function
# =============================================================================
CLEANER_REGISTRY = {
    'Pendidikan_APM_provinsi.csv': {
        'cleaner': 'custom',
        'function': clean_apm,
    },
    'Kesehatan_angka_harapan_hidup.csv': {
        'cleaner': 'custom',
        'function': clean_ahh,
    },
    'Ekonomi_persentase_penduduk_miskin.csv': {
        'cleaner': 'custom',
        'function': clean_poverty,
    },
    'Ekonomi_upah_rata-rata.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Upah_Rata_Rata',
            'category': 'Ekonomi',
            'dimension': None,
            'satuan': 'Rupiah/Jam'
        }
    },
    'Kesehatan_unmet_layanan_kesehatan.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Unmet_Layanan_Kesehatan',
            'category': 'Kesehatan',
            'dimension': None,
            'satuan': 'Persen'
        }
    },
    'Ketenagakerjaan_formal.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Tenaga_Kerja_Formal',
            'category': 'Ketenagakerjaan',
            'dimension': None,
            'satuan': 'Persen'
        }
    },
    'Ketenagakerjaan_informal.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Lapangan_Kerja_Informal',
            'category': 'Ketenagakerjaan',
            'dimension': None,
            'satuan': 'Persen'
        }
    },
    'Pendidikan_APK_PT_provinsi.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'APK_Perguruan_Tinggi',
            'category': 'Pendidikan',
            'dimension': None,
            'satuan': 'Persen'
        }
    },
    'Pendidikan_Rata-rata_lama_sekolah.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Rata_Rata_Lama_Sekolah',
            'category': 'Pendidikan',
            'dimension': None,
            'satuan': 'Tahun'
        }
    },
    'Teknologi_memiliki_telepon_seluler.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Memiliki_Telepon_Seluler',
            'category': 'Teknologi',
            'dimension': 'Perkotaan+Perdesaan',
            'satuan': 'Persen'
        }
    },
    'Teknologi_mengakses_internet.csv': {
        'cleaner': 'simple',
        'function': clean_simple,
        'params': {
            'indicator_name': 'Mengakses_Internet',
            'category': 'Teknologi',
            'dimension': 'Perkotaan+Perdesaan',
            'satuan': 'Persen'
        }
    },
}


def get_cleaner(filename):
    """
    Get the appropriate cleaner function for a CSV file.
    
    Args:
        filename: Name of CSV file
        
    Returns:
        Tuple of (cleaner_function, params) or None if not found
        
    Raises:
        ValueError: If cleaner not found for filename
    """
    if filename not in CLEANER_REGISTRY:
        raise ValueError(f"No cleaner registered for {filename}")
    
    config = CLEANER_REGISTRY[filename]
    return config
