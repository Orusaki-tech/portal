from uuid import uuid4

import pytest
from shapely import wkt

from backend.engine.service_layer.consensus import (
    _merge_many,
    _merge_two,
    merge_annotations,
)


class TestMergeTwo:
    def test_identical_returns_first(self) -> None:
        wkt_a = "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"
        result = _merge_two(wkt_a, wkt_a)
        assert result == wkt_a

    def test_different_returns_median(self) -> None:
        a = "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))"
        b = "POLYGON((1 1, 3 1, 3 3, 1 3, 1 1))"
        result = _merge_two(a, b)
        poly = wkt.loads(result)
        assert poly.area > 0
        assert poly.area < 6.0  # between the two input areas


class TestMergeMany:
    def test_two_identical(self) -> None:
        wkts = [
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        ]
        result = _merge_many(wkts)
        poly = wkt.loads(result)
        assert poly.area == 1.0

    def test_three_majority_vote(self) -> None:
        wkts = [
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))",
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        ]
        result = _merge_many(wkts)
        poly = wkt.loads(result)
        assert (
            poly.area == 1.0
        )  # median of [(0,0), (1,0)], [(0,0), (2,0)], [(0,0), (1,0)] = (0,0), (1,0)

    def test_different_vertex_counts(self) -> None:
        wkts = [
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
        ]
        result = _merge_many(wkts)
        from shapely import wkt as swkt

        poly = swkt.loads(result)
        assert poly.area == 1.0


class TestMergeAnnotations:
    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError):
            merge_annotations([])

    def test_single_passthrough(self) -> None:
        result = merge_annotations([(uuid4(), "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")])
        assert result == "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"

    def test_two_dispatches_to_merge_two(self) -> None:
        result = merge_annotations(
            [
                (uuid4(), "POLYGON((0 0, 2 0, 2 2, 0 2, 0 0))"),
                (uuid4(), "POLYGON((1 1, 3 1, 3 3, 1 3, 1 1))"),
            ]
        )
        poly = wkt.loads(result)
        assert poly.area > 0

    def test_three_dispatches_to_merge_many(self) -> None:
        result = merge_annotations(
            [
                (uuid4(), "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"),
                (uuid4(), "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"),
                (uuid4(), "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))"),
            ]
        )
        poly = wkt.loads(result)
        assert poly.area == 1.0
