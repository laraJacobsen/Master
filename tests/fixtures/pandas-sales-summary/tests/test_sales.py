from solution import load_sales, revenue_by_region


def test_revenue_column():
    df = load_sales()
    assert "revenue" in df.columns
    assert df.loc[0, "revenue"] == 42.0  # 12 notebooks at 3.50


def test_keeps_every_row():
    assert len(load_sales()) == 12


def test_largest_region_first():
    totals = revenue_by_region(load_sales())
    assert list(totals.index) == ["north", "east", "west", "south"]
