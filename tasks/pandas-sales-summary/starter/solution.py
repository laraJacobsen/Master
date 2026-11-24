import pandas as pd


def load_sales(path="data/sales.csv"):
    """Read the sales CSV and add a "revenue" column (units * unit_price)."""
    df = pd.read_csv(path)
    # TODO: add the revenue column
    return df


def revenue_by_region(df):
    """Total revenue per region, largest first, as a Series indexed by region."""
    # TODO
    return None
