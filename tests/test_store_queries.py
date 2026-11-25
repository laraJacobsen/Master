"""update_question interpolates column names into its UPDATE (they can't be ?
parameters), so it must refuse any key that isn't an editable questions column."""

import pytest

from backend import store


def _draft():
    return store.create_question({"title": "Query safety", "prompt": "p", "language": "python",
                                  "test_cases": [], "reference_solution": "print(1)"})


def test_update_question_accepts_real_columns():
    qid = _draft()
    store.update_question(qid, {"title": "Renamed", "validated": 1})
    row = store.get_question_row(qid)
    assert row["title"] == "Renamed" and row["validated"]


@pytest.mark.parametrize("key", [
    "title = 'x' --",                       # injection through a column name
    "title = (SELECT 1) WHERE 1=1; --",
    "no_such_column",
    "id",                                    # real, but not editable
    "created_at",
])
def test_update_question_rejects_other_keys(key):
    qid = _draft()
    with pytest.raises(ValueError):
        store.update_question(qid, {key: "x"})
    assert store.get_question_row(qid)["title"] == "Query safety"
