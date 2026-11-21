import pandas as pd

from stages_cleaning.provenance import build_stage_id


def test_stage_id_is_deterministic_and_order_independent():
    frame = pd.DataFrame({"a": ["x", "y"], "b": ["1", "2"]})
    ids = build_stage_id(frame)
    reversed_frame = frame.iloc[::-1].reset_index(drop=True)
    reversed_ids = build_stage_id(reversed_frame)
    assert ids.iloc[0] == reversed_ids.iloc[1]
    assert ids.iloc[1] == reversed_ids.iloc[0]
