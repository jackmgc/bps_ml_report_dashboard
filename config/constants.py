"""Constants - canonical lists and configurations"""

# Provinces to DROP during extraction
# These are the 4 new PAPUA pemekaran provinces with mostly empty/dash data (only partial 2024)
DROPPED_PROVINCES = [
    "PAPUA BARAT DAYA",
    "PAPUA SELATAN",
    "PAPUA TENGAH",
    "PAPUA PEGUNUNGAN",
]

# Non-province rows that appear in CSV footers
NON_PROVINCE_ROWS = [
    "Catatan",
    "Sumber",
    "Source",
    "Note",
]

# Canonical province list (35 total: 34 provinces + INDONESIA national aggregate)
# Excludes: PAPUA BARAT DAYA, PAPUA SELATAN, PAPUA TENGAH, PAPUA PEGUNUNGAN
CANONICAL_PROVINCES = [
    "ACEH",
    "SUMATERA UTARA",
    "SUMATERA BARAT",
    "RIAU",
    "JAMBI",
    "SUMATERA SELATAN",
    "BENGKULU",
    "LAMPUNG",
    "KEP. BANGKA BELITUNG",
    "KEP. RIAU",
    "DKI JAKARTA",
    "JAWA BARAT",
    "JAWA TENGAH",
    "DI YOGYAKARTA",
    "JAWA TIMUR",
    "BANTEN",
    "BALI",
    "NUSA TENGGARA BARAT",
    "NUSA TENGGARA TIMUR",
    "KALIMANTAN BARAT",
    "KALIMANTAN TENGAH",
    "KALIMANTAN SELATAN",
    "KALIMANTAN TIMUR",
    "KALIMANTAN UTARA",
    "SULAWESI UTARA",
    "SULAWESI TENGAH",
    "SULAWESI SELATAN",
    "SULAWESI TENGGARA",
    "GORONTALO",
    "SULAWESI BARAT",
    "MALUKU",
    "MALUKU UTARA",
    "PAPUA BARAT",
    "PAPUA",
    "INDONESIA",  # National aggregate
]

# Years available in datasets
YEAR_RANGE_2020_2024 = [2020, 2021, 2022, 2023, 2024]
YEAR_RANGE_2021_2025 = [2021, 2022, 2023, 2024, 2025]

# CSV file names
CSV_FILES = [
    "Ekonomi_persentase_penduduk_miskin.csv",
    "Ekonomi_upah_rata-rata.csv",
    "Kesehatan_angka_harapan_hidup.csv",
    "Kesehatan_unmet_layanan_kesehatan.csv",
    "Ketenagakerjaan_formal.csv",
    "Ketenagakerjaan_informal.csv",
    "Pendidikan_APK_PT_provinsi.csv",
    "Pendidikan_APM_provinsi.csv",
    "Pendidikan_Rata-rata_lama_sekolah.csv",
    "Teknologi_memiliki_telepon_seluler.csv",
    "Teknologi_mengakses_internet.csv",
]

# Header row indices for each CSV (0-indexed)
# Rows 0-3 are metadata, data starts from row 4
CSV_HEADER_ROWS = 4  # Skip first 4 rows (metadata)

# Data quality flag categories
DATA_QUALITY_FLAGS = [
    None,  # VALID (no flag)
    "OUTLIER",
    "MISSING_DATA",
    "INCONSISTENT",
]

# Numeric range validations (kategori -> (min, max))
NUMERIC_RANGES = {
    "Persen": (0.0, 100.0),
    "Tahun": (50.0, 85.0),  # Life expectancy range
    "Rupiah/Jam": (10000.0, 50000.0),  # Wage range estimate
}

# Decimal places for normalization
DECIMAL_PLACES = 4

# Row count expectations per file (province rows before unpivot)
# Used for reconciliation validation
# 35 = 34 canonical provinces + 1 INDONESIA aggregate
EXPECTED_ROW_COUNTS = {
    "Ekonomi_persentase_penduduk_miskin.csv": 35,  # 34 provinces + 1 INDONESIA
    "Ekonomi_upah_rata-rata.csv": 35,
    "Kesehatan_angka_harapan_hidup.csv": 70,  # 35 × 2 (gender split)
    "Kesehatan_unmet_layanan_kesehatan.csv": 35,
    "Ketenagakerjaan_formal.csv": 35,
    "Ketenagakerjaan_informal.csv": 35,
    "Pendidikan_APK_PT_provinsi.csv": 35,
    "Pendidikan_APM_provinsi.csv": 105,  # 35 × 3 (SD, SMP, SM)
    "Pendidikan_Rata-rata_lama_sekolah.csv": 35,
    "Teknologi_memiliki_telepon_seluler.csv": 35,
    "Teknologi_mengakses_internet.csv": 35,
}

# Total expected indicators after normalization
TOTAL_EXPECTED_INDICATORS = 14  # 11 base indicators + 3 APM dimensions + 2 AHH genders - 2 base

# Total expected rows in staging table
# = 35 provinces × 5 years × (8 single + 3 APM dims + 2 AHH genders) = 2450 (approx)
# Poverty uses 2021-2025, others 2020-2024
EXPECTED_STAGING_ROWS = 2450
