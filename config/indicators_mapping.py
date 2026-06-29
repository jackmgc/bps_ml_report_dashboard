"""Indicators mapping - defines all metrics, categories, units, and sources"""

INDICATORS_MAPPING = {
    # EKONOMI (Economy)
    "ekonomi_miskin": {
        "kategori": "Ekonomi",
        "nama_indikator": "Persentase Penduduk Miskin",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Ekonomi_persentase_penduduk_miskin.csv",
        "year_range": [2021, 2022, 2023, 2024, 2025],
    },
    "ekonomi_upah": {
        "kategori": "Ekonomi",
        "nama_indikator": "Upah Rata-rata Per Jam Pekerja",
        "satuan": "Rupiah/Jam",
        "sumber": "Sakernas",
        "dimensi": None,
        "csv_file": "Ekonomi_upah_rata-rata.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    
    # KESEHATAN (Health)
    "kesehatan_ahh_male": {
        "kategori": "Kesehatan",
        "nama_indikator": "Angka Harapan Hidup",
        "satuan": "Tahun",
        "sumber": "BPS",
        "dimensi": "Laki-laki",
        "csv_file": "Kesehatan_angka_harapan_hidup.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "kesehatan_ahh_female": {
        "kategori": "Kesehatan",
        "nama_indikator": "Angka Harapan Hidup",
        "satuan": "Tahun",
        "sumber": "BPS",
        "dimensi": "Perempuan",
        "csv_file": "Kesehatan_angka_harapan_hidup.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "kesehatan_unmet": {
        "kategori": "Kesehatan",
        "nama_indikator": "Persentase Unmet Need Pelayanan Kesehatan",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Kesehatan_unmet_layanan_kesehatan.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    
    # KETENAGAKERJAAN (Employment)
    "ketenagakerjaan_formal": {
        "kategori": "Ketenagakerjaan",
        "nama_indikator": "Persentase Tenaga Kerja Formal",
        "satuan": "Persen",
        "sumber": "Sakernas",
        "dimensi": None,
        "csv_file": "Ketenagakerjaan_formal.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "ketenagakerjaan_informal": {
        "kategori": "Ketenagakerjaan",
        "nama_indikator": "Proporsi Lapangan Kerja Informal Sektor Non-Pertanian",
        "satuan": "Persen",
        "sumber": "BPS",
        "dimensi": None,
        "csv_file": "Ketenagakerjaan_informal.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    
    # PENDIDIKAN (Education)
    "pendidikan_apk_pt": {
        "kategori": "Pendidikan",
        "nama_indikator": "Angka Partisipasi Kasar PT",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Pendidikan_APK_PT_provinsi.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "pendidikan_apm_sd": {
        "kategori": "Pendidikan",
        "nama_indikator": "Angka Partisipasi Murni",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": "SD/sederajat",
        "csv_file": "Pendidikan_APM_provinsi.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "pendidikan_apm_smp": {
        "kategori": "Pendidikan",
        "nama_indikator": "Angka Partisipasi Murni",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": "SMP/sederajat",
        "csv_file": "Pendidikan_APM_provinsi.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "pendidikan_apm_sm": {
        "kategori": "Pendidikan",
        "nama_indikator": "Angka Partisipasi Murni",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": "SM/sederajat",
        "csv_file": "Pendidikan_APM_provinsi.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "pendidikan_lama_sekolah": {
        "kategori": "Pendidikan",
        "nama_indikator": "Rata-rata Lama Sekolah",
        "satuan": "Tahun",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Pendidikan_Rata-rata_lama_sekolah.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    
    # TEKNOLOGI (Technology)
    "teknologi_telepon": {
        "kategori": "Teknologi",
        "nama_indikator": "Persentase Penduduk Memiliki Telepon Seluler",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Teknologi_memiliki_telepon_seluler.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
    "teknologi_internet": {
        "kategori": "Teknologi",
        "nama_indikator": "Persentase Penduduk Mengakses Internet",
        "satuan": "Persen",
        "sumber": "Susenas",
        "dimensi": None,
        "csv_file": "Teknologi_mengakses_internet.csv",
        "year_range": [2020, 2021, 2022, 2023, 2024],
    },
}

# Reverse mapping: CSV file name -> list of indicator IDs
CSV_TO_INDICATORS = {}
for ind_id, ind_info in INDICATORS_MAPPING.items():
    csv_file = ind_info["csv_file"]
    if csv_file not in CSV_TO_INDICATORS:
        CSV_TO_INDICATORS[csv_file] = []
    CSV_TO_INDICATORS[csv_file].append(ind_id)
