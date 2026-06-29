"""Aggregator module - creates ML-ready aggregated tables from DW fact/dimension tables"""
import pandas as pd
from sqlalchemy import create_engine, text, MetaData, inspect
from sqlalchemy.exc import SQLAlchemyError
from config.db_config import PSQL_CONNECTION_STRING
from utils.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# DDL: Create dm schema and tables
# ============================================================================

CREATE_DM_SCHEMA = """
DROP SCHEMA IF EXISTS dm CASCADE;
CREATE SCHEMA IF NOT EXISTS dm;
"""

# Table 1: Aggregated by province (K-MEANS/HDBSCAN)
CREATE_AGG_PROVINCE_ML_TABLE = """
CREATE TABLE IF NOT EXISTS dm.agg_province_ml (
    provinsi_id INTEGER PRIMARY KEY REFERENCES dw.dim_provinsi(provinsi_id),
    provinsi VARCHAR(255) NOT NULL UNIQUE,
    -- Predictors: Ekonomi
    ekonomi_miskin_mean NUMERIC(15, 4),
    ekonomi_miskin_trend_pct NUMERIC(15, 4),
    ekonomi_upah_mean NUMERIC(15, 4),
    ekonomi_upah_trend_pct NUMERIC(15, 4),
    -- Predictors: Kesehatan (separate by gender)
    kesehatan_ahh_laki_mean NUMERIC(15, 4),
    kesehatan_ahh_laki_trend_pct NUMERIC(15, 4),
    kesehatan_ahh_perempuan_mean NUMERIC(15, 4),
    kesehatan_ahh_perempuan_trend_pct NUMERIC(15, 4),
    kesehatan_unmet_mean NUMERIC(15, 4),
    kesehatan_unmet_trend_pct NUMERIC(15, 4),
    -- Predictors: Ketenagakerjaan
    ketenagakerjaan_formal_mean NUMERIC(15, 4),
    ketenagakerjaan_formal_trend_pct NUMERIC(15, 4),
    ketenagakerjaan_informal_mean NUMERIC(15, 4),
    ketenagakerjaan_informal_trend_pct NUMERIC(15, 4),
    -- Predictors: Teknologi
    teknologi_telepon_mean NUMERIC(15, 4),
    teknologi_telepon_trend_pct NUMERIC(15, 4),
    teknologi_internet_mean NUMERIC(15, 4),
    teknologi_internet_trend_pct NUMERIC(15, 4),
    -- Targets: Pendidikan (mean only)
    apm_sd_mean NUMERIC(15, 4),
    apm_smp_mean NUMERIC(15, 4),
    apm_sm_mean NUMERIC(15, 4),
    apk_pt_mean NUMERIC(15, 4),
    rata_rata_lama_sekolah_mean NUMERIC(15, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_agg_prov_provinsi ON dm.agg_province_ml(provinsi);
"""

# Table 2: Time series by province and year (Spearman/LR/RF)
CREATE_TIMESERIES_PROVINCE_YEAR_ML_TABLE = """
CREATE TABLE IF NOT EXISTS dm.timeseries_province_year_ml (
    provinsi_id INTEGER NOT NULL REFERENCES dw.dim_provinsi(provinsi_id),
    tahun_id INTEGER NOT NULL REFERENCES dw.dim_time(tahun_id),
    tahun INTEGER NOT NULL,
    provinsi VARCHAR(255) NOT NULL,
    -- Predictors: raw values
    ekonomi_miskin NUMERIC(15, 4),
    ekonomi_upah_rata_rata NUMERIC(15, 4),
    kesehatan_ahh_laki NUMERIC(15, 4),
    kesehatan_ahh_perempuan NUMERIC(15, 4),
    kesehatan_unmet_layanan NUMERIC(15, 4),
    ketenagakerjaan_formal NUMERIC(15, 4),
    ketenagakerjaan_informal NUMERIC(15, 4),
    teknologi_telepon_seluler NUMERIC(15, 4),
    teknologi_internet NUMERIC(15, 4),
    -- Targets: raw values
    apm_sd NUMERIC(15, 4),
    apm_smp NUMERIC(15, 4),
    apm_sm NUMERIC(15, 4),
    apk_pt NUMERIC(15, 4),
    rata_rata_lama_sekolah NUMERIC(15, 4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (provinsi_id, tahun_id),
    CONSTRAINT chk_tahun_range CHECK (tahun IN (2020, 2021, 2022, 2023, 2024))
);
CREATE INDEX IF NOT EXISTS idx_ts_prov_year ON dm.timeseries_province_year_ml(provinsi, tahun);
CREATE INDEX IF NOT EXISTS idx_ts_tahun ON dm.timeseries_province_year_ml(tahun);
"""

# ============================================================================
# Refresh Functions (SQL)
# ============================================================================

REFRESH_AGG_PROVINCE_ML = """
CREATE OR REPLACE FUNCTION dm.refresh_agg_province_ml()
RETURNS TABLE(rows_inserted INTEGER) AS $$
DECLARE
    v_rows_inserted INTEGER := 0;
BEGIN
    TRUNCATE TABLE dm.agg_province_ml;
    
    INSERT INTO dm.agg_province_ml (
        provinsi_id, provinsi,
        ekonomi_miskin_mean, ekonomi_miskin_trend_pct,
        ekonomi_upah_mean, ekonomi_upah_trend_pct,
        kesehatan_ahh_laki_mean, kesehatan_ahh_laki_trend_pct,
        kesehatan_ahh_perempuan_mean, kesehatan_ahh_perempuan_trend_pct,
        kesehatan_unmet_mean, kesehatan_unmet_trend_pct,
        ketenagakerjaan_formal_mean, ketenagakerjaan_formal_trend_pct,
        ketenagakerjaan_informal_mean, ketenagakerjaan_informal_trend_pct,
        teknologi_telepon_mean, teknologi_telepon_trend_pct,
        teknologi_internet_mean, teknologi_internet_trend_pct,
        apm_sd_mean, apm_smp_mean, apm_sm_mean, apk_pt_mean, rata_rata_lama_sekolah_mean
    )
    SELECT
        dp.provinsi_id,
        dp.provinsi_name,
        -- Ekonomi Miskin (lagged: use 2021-2025 data to represent 2020-2024)
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin')
                  AND dt.tahun BETWEEN 2021 AND 2025
                  THEN fi.nilai END) AS ekonomi_miskin_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin') 
                           AND dt.tahun = 2021 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin')
                         AND dt.tahun = 2025 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin')
                         AND dt.tahun = 2021 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin')
                          AND dt.tahun = 2021 THEN fi.nilai END) * 100
             ELSE NULL END AS ekonomi_miskin_trend_pct,
        -- Ekonomi Upah
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS ekonomi_upah_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS ekonomi_upah_trend_pct,
        -- Kesehatan AHH Laki-laki
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                  AND did.dimensi_name = 'Laki-laki'
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS kesehatan_ahh_laki_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                           AND did.dimensi_name = 'Laki-laki' AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                         AND did.dimensi_name = 'Laki-laki' AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                         AND did.dimensi_name = 'Laki-laki' AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                          AND did.dimensi_name = 'Laki-laki' AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS kesehatan_ahh_laki_trend_pct,
        -- Kesehatan AHH Perempuan
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                  AND did.dimensi_name = 'Perempuan'
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS kesehatan_ahh_perempuan_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                           AND did.dimensi_name = 'Perempuan' AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                         AND did.dimensi_name = 'Perempuan' AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                         AND did.dimensi_name = 'Perempuan' AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                          AND did.dimensi_name = 'Perempuan' AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS kesehatan_ahh_perempuan_trend_pct,
        -- Kesehatan Unmet
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS kesehatan_unmet_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS kesehatan_unmet_trend_pct,
        -- Ketenagakerjaan Formal
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS ketenagakerjaan_formal_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS ketenagakerjaan_formal_trend_pct,
        -- Ketenagakerjaan Informal
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS ketenagakerjaan_informal_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS ketenagakerjaan_informal_trend_pct,
        -- Teknologi Telepon
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS teknologi_telepon_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS teknologi_telepon_trend_pct,
        -- Teknologi Internet
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS teknologi_internet_mean,
        CASE WHEN AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                           AND dt.tahun = 2020 THEN fi.nilai END) > 0
             THEN (
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                         AND dt.tahun = 2024 THEN fi.nilai END) -
                AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                         AND dt.tahun = 2020 THEN fi.nilai END)
             ) / AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                          AND dt.tahun = 2020 THEN fi.nilai END) * 100
             ELSE NULL END AS teknologi_internet_trend_pct,
        -- Targets: APM-SD, APM-SMP, APM-SM
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                  AND did.dimensi_name = 'APM-SD'
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS apm_sd_mean,
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                  AND did.dimensi_name = 'APM-SMP'
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS apm_smp_mean,
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                  AND did.dimensi_name = 'APM-SM'
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS apm_sm_mean,
        -- Target: APK-PT
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APK_Perguruan_Tinggi')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS apk_pt_mean,
        -- Target: Rata-rata Lama Sekolah
        AVG(CASE WHEN did.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Rata_Rata_Lama_Sekolah')
                  AND dt.tahun BETWEEN 2020 AND 2024
                  THEN fi.nilai END) AS rata_rata_lama_sekolah_mean
    FROM dw.dim_provinsi dp
    LEFT JOIN dw.fact_indikator fi ON fi.provinsi_id = dp.provinsi_id
    LEFT JOIN dw.dim_time dt ON fi.tahun_id = dt.tahun_id
    LEFT JOIN dw.dim_indikator_dimensi did ON fi.indikator_dimensi_id = did.indikator_dimensi_id
    WHERE dt.tahun IS NULL OR (dt.tahun BETWEEN 2020 AND 2025)
    GROUP BY dp.provinsi_id, dp.provinsi_name;
    
    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;
    RETURN QUERY SELECT v_rows_inserted;
END;
$$ LANGUAGE plpgsql;
"""

REFRESH_TIMESERIES_PROVINCE_YEAR_ML = """
CREATE OR REPLACE FUNCTION dm.refresh_timeseries_province_year_ml()
RETURNS TABLE(rows_inserted INTEGER) AS $$
DECLARE
    v_rows_inserted INTEGER := 0;
BEGIN
    TRUNCATE TABLE dm.timeseries_province_year_ml;
    
    WITH base_data AS (
        SELECT
            dp.provinsi_id,
            dt.tahun_id,
            dt.tahun,
            dp.provinsi_name,
            did.indikator_id,
            did.dimensi_name,
            fi.nilai
        FROM dw.dim_provinsi dp
        CROSS JOIN dw.dim_time dt
        LEFT JOIN dw.fact_indikator fi ON fi.provinsi_id = dp.provinsi_id AND fi.tahun_id = dt.tahun_id
        LEFT JOIN dw.dim_indikator_dimensi did ON fi.indikator_dimensi_id = did.indikator_dimensi_id
        WHERE dt.tahun BETWEEN 2020 AND 2025
    ),
    lagged_miskin AS (
        SELECT
            provinsi_id,
            tahun - 1 as target_year,
            nilai as ekonomi_miskin
        FROM base_data
        WHERE indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Persentase_Penduduk_Miskin')
        AND tahun BETWEEN 2021 AND 2025
    )
    INSERT INTO dm.timeseries_province_year_ml (
        provinsi_id, tahun_id, tahun, provinsi,
        ekonomi_miskin, ekonomi_upah_rata_rata,
        kesehatan_ahh_laki, kesehatan_ahh_perempuan, kesehatan_unmet_layanan,
        ketenagakerjaan_formal, ketenagakerjaan_informal,
        teknologi_telepon_seluler, teknologi_internet,
        apm_sd, apm_smp, apm_sm, apk_pt, rata_rata_lama_sekolah
    )
    SELECT
        bd.provinsi_id,
        bd.tahun_id,
        bd.tahun,
        bd.provinsi_name,
        MAX(CASE WHEN lm.ekonomi_miskin IS NOT NULL THEN lm.ekonomi_miskin ELSE NULL END) AS ekonomi_miskin,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Upah_Rata_Rata')
                 THEN bd.nilai END) AS ekonomi_upah_rata_rata,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                 AND bd.dimensi_name = 'Laki-laki'
                 THEN bd.nilai END) AS kesehatan_ahh_laki,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'AHH')
                 AND bd.dimensi_name = 'Perempuan'
                 THEN bd.nilai END) AS kesehatan_ahh_perempuan,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Unmet_Layanan_Kesehatan')
                 THEN bd.nilai END) AS kesehatan_unmet_layanan,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Tenaga_Kerja_Formal')
                 THEN bd.nilai END) AS ketenagakerjaan_formal,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Lapangan_Kerja_Informal')
                 THEN bd.nilai END) AS ketenagakerjaan_informal,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Memiliki_Telepon_Seluler')
                 THEN bd.nilai END) AS teknologi_telepon_seluler,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Mengakses_Internet')
                 THEN bd.nilai END) AS teknologi_internet,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                 AND bd.dimensi_name = 'APM-SD'
                 THEN bd.nilai END) AS apm_sd,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                 AND bd.dimensi_name = 'APM-SMP'
                 THEN bd.nilai END) AS apm_smp,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APM')
                 AND bd.dimensi_name = 'APM-SM'
                 THEN bd.nilai END) AS apm_sm,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'APK_Perguruan_Tinggi')
                 THEN bd.nilai END) AS apk_pt,
        MAX(CASE WHEN bd.indikator_id = (SELECT indikator_id FROM dw.dim_indikator WHERE indikator_name = 'Rata_Rata_Lama_Sekolah')
                 THEN bd.nilai END) AS rata_rata_lama_sekolah
    FROM base_data bd
    LEFT JOIN lagged_miskin lm ON bd.provinsi_id = lm.provinsi_id AND bd.tahun = lm.target_year
    WHERE bd.tahun BETWEEN 2020 AND 2024
    GROUP BY bd.provinsi_id, bd.tahun_id, bd.tahun, bd.provinsi_name;
    
    GET DIAGNOSTICS v_rows_inserted = ROW_COUNT;
    RETURN QUERY SELECT v_rows_inserted;
END;
$$ LANGUAGE plpgsql;
"""

# ============================================================================
# Helper Functions
# ============================================================================

def execute_ddl(engine, ddl_statement, description=""):
    """Execute DDL statement and return success status"""
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
        else:
            logger.info(f"[SKIP] {description} - Already exists")
            return True
    except Exception as e:
        logger.error(f"[FAIL] {description}: {str(e)}")
        return False


def execute_function(engine, function_name, description=""):
    """Execute a PostgreSQL function"""
    try:
        with engine.connect() as conn:
            result = conn.execute(text(f"SELECT * FROM {function_name}();"))
            rows_inserted = result.fetchone()[0]
            conn.commit()
        logger.info(f"[OK] {description} - {rows_inserted} rows inserted")
        return rows_inserted
    except Exception as e:
        logger.error(f"[FAIL] {description}: {str(e)}")
        return 0


# ============================================================================
# Main Aggregation Setup & Refresh Functions
# ============================================================================

def setup_aggregation_schema():
    """Create dm schema, tables, and refresh functions"""
    engine = create_engine(PSQL_CONNECTION_STRING)
    
    logger.info("=" * 80)
    logger.info("Setting up Data Mart (dm) schema for ML aggregations")
    logger.info("=" * 80)
    
    # Create schema
    execute_ddl(engine, CREATE_DM_SCHEMA, "Create dm schema")
    
    # Create tables
    execute_ddl(engine, CREATE_AGG_PROVINCE_ML_TABLE, "Create dm.agg_province_ml table")
    execute_ddl(engine, CREATE_TIMESERIES_PROVINCE_YEAR_ML_TABLE, "Create dm.timeseries_province_year_ml table")
    
    # Create refresh functions
    execute_ddl(engine, REFRESH_AGG_PROVINCE_ML, "Create dm.refresh_agg_province_ml() function")
    execute_ddl(engine, REFRESH_TIMESERIES_PROVINCE_YEAR_ML, "Create dm.refresh_timeseries_province_year_ml() function")
    
    logger.info("=" * 80)
    logger.info("Data Mart schema setup complete")
    logger.info("=" * 80)
    
    engine.dispose()


def refresh_data_mart():
    """Refresh all aggregation tables by executing their refresh functions"""
    engine = create_engine(PSQL_CONNECTION_STRING)
    
    logger.info("=" * 80)
    logger.info("Refreshing Data Mart aggregation tables")
    logger.info("=" * 80)
    
    # Refresh agg_province_ml
    rows1 = execute_function(
        engine,
        "dm.refresh_agg_province_ml",
        "Refresh dm.agg_province_ml (aggregated by province)"
    )
    
    # Refresh timeseries_province_year_ml
    rows2 = execute_function(
        engine,
        "dm.refresh_timeseries_province_year_ml",
        "Refresh dm.timeseries_province_year_ml (province x year time series)"
    )
    
    logger.info("=" * 80)
    logger.info(f"Data Mart refresh complete: {rows1} province aggregates, {rows2} time series records")
    logger.info("=" * 80)
    
    engine.dispose()
    
    return rows1, rows2


def aggregate_for_clustering():
    """
    Retrieve aggregated province table for K-MEANS/HDBSCAN clustering
    
    Returns:
        pd.DataFrame: 35 provinces × 35 columns (mean + trend for predictors, mean-only for targets)
    """
    engine = create_engine(PSQL_CONNECTION_STRING)
    
    query = """
    SELECT *
    FROM dm.agg_province_ml
    ORDER BY provinsi
    """
    
    df = pd.read_sql(query, engine)
    engine.dispose()
    
    logger.info(f"[OK] Loaded clustering aggregation table: {df.shape[0]} provinces, {df.shape[1]} columns")
    logger.info(f"     Columns: {list(df.columns)}")
    
    return df


def aggregate_for_timeseries():
    """
    Retrieve time series table for Spearman correlation, linear regression, random forest
    
    Returns:
        pd.DataFrame: ~175 rows (35 provinces × 5 years), 23 columns (province, year + predictors + targets)
    """
    engine = create_engine(PSQL_CONNECTION_STRING)
    
    query = """
    SELECT *
    FROM dm.timeseries_province_year_ml
    ORDER BY provinsi, tahun
    """
    
    df = pd.read_sql(query, engine)
    engine.dispose()
    
    logger.info(f"[OK] Loaded time series table: {df.shape[0]} records, {df.shape[1]} columns")
    logger.info(f"     Years available: {sorted(df['tahun'].unique().tolist())}")
    logger.info(f"     Provinces: {df['provinsi'].nunique()}")
    
    return df


def validate_aggregations():
    """Validate aggregation tables: row counts, year range, NULL detection"""
    engine = create_engine(PSQL_CONNECTION_STRING)
    
    logger.info("=" * 80)
    logger.info("Validating Data Mart aggregations")
    logger.info("=" * 80)
    
    try:
        # Check agg_province_ml
        with engine.connect() as conn:
            result = conn.execute(text(
                "SELECT COUNT(*) FROM dm.agg_province_ml;"
            ))
            count1 = result.fetchone()[0]
            logger.info(f"dm.agg_province_ml: {count1} rows (expected 35)")
            if count1 != 35:
                logger.warning(f"  ⚠️  Expected 35 provinces, got {count1}")
            
            # Check timeseries_province_year_ml
            result = conn.execute(text(
                "SELECT COUNT(*) FROM dm.timeseries_province_year_ml;"
            ))
            count2 = result.fetchone()[0]
            logger.info(f"dm.timeseries_province_year_ml: {count2} rows (expected 175)")
            if count2 != 175:
                logger.warning(f"  ⚠️  Expected 175 province-year combinations, got {count2}")
            
            # Check year range in timeseries
            result = conn.execute(text(
                "SELECT DISTINCT tahun FROM dm.timeseries_province_year_ml ORDER BY tahun;"
            ))
            years = [row[0] for row in result.fetchall()]
            logger.info(f"Years in timeseries: {years}")
            expected_years = [2020, 2021, 2022, 2023, 2024]
            if years != expected_years:
                logger.warning(f"  ⚠️  Expected years {expected_years}, got {years}")
            
            # Check for NULLs in critical columns
            result = conn.execute(text(
                """SELECT COUNT(*) FROM dm.agg_province_ml 
                   WHERE ekonomi_miskin_mean IS NULL 
                      OR ekonomi_upah_mean IS NULL 
                      OR apm_sd_mean IS NULL;"""
            ))
            null_count = result.fetchone()[0]
            if null_count > 0:
                logger.warning(f"  ⚠️  Found {null_count} provinces with NULL values in key columns")
            else:
                logger.info("  [OK] No NULL values in critical predictor/target columns")
        
        logger.info("=" * 80)
        logger.info("Validation complete")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    """Quick test when running module directly"""
    setup_aggregation_schema()
    refresh_data_mart()
    validate_aggregations()
    
    print("\n" + "=" * 80)
    print("Testing data retrieval...")
    print("=" * 80)
    df_clustering = aggregate_for_clustering()
    print(f"\nClustering table:\n{df_clustering.head()}")
    
    df_timeseries = aggregate_for_timeseries()
    print(f"\nTimeseries table:\n{df_timeseries.head()}")