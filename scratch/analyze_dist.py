
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
import matplotlib.pyplot as plt
PSQL_CONNECTION_STRING = 'postgresql://postgres:postgres@localhost:5432/postgres'

def analyze_distributions():
    engine = create_engine(PSQL_CONNECTION_STRING)
    df = pd.read_sql("SELECT * FROM dm.agg_province_ml", engine)
    
    # Select predictors and targets
    cols = [c for c in df.columns if c.endswith('_mean')]
    
    print("Column,Skewness,Kurtosis")
    for col in cols:
        print(f"{col},{df[col].skew():.4f},{df[col].kurtosis():.4f}")

if __name__ == "__main__":
    analyze_distributions()
