import pandas as pd

from solution import load_sales, revenue_by_region


def test_missing_units_count_as_zero():
    df = load_sales()
    assert df["revenue"].isna().sum() == 0
    assert df.loc[5, "revenue"] == 0


def test_uses_the_dataframe_it_is_given():
    df = pd.DataFrame({
        "region": ["a", "b", "a"],
        "units": [1, 2, 3],
        "unit_price": [1.0, 1.0, 1.0],
        "revenue": [1.0, 2.0, 3.0],
    })
    totals = revenue_by_region(df)
    assert list(totals.index) == ["a", "b"]
    assert totals.tolist() == [4.0, 2.0]
