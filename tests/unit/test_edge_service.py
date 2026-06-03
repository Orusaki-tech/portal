from backend.engine.service_layer.edge_service import (
    _heuristic_confidence,
    _wkt_to_coords,
    validate_polygon,
)


class TestWktToCoords:
    def test_parses_square(self) -> None:
        coords = _wkt_to_coords("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        assert len(coords) == 5
        assert coords[0] == (0.0, 0.0)
        assert coords[2] == (1.0, 1.0)


class TestHeuristicConfidence:
    def test_perfect_square_high_confidence(self) -> None:
        confidence, ambiguous = _heuristic_confidence("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        assert 0.70 <= confidence <= 1.0
        assert not ambiguous

    def test_sliver_low_confidence(self) -> None:
        confidence, ambiguous = _heuristic_confidence("POLYGON((0 0, 1 0, 1 0.001, 0 0.001, 0 0))")
        assert confidence < 0.70
        assert ambiguous

    def test_degenerate_returns_zero(self) -> None:
        confidence, ambiguous = _heuristic_confidence("POLYGON((0 0, 1 0, 0 0))")
        assert confidence == 0.0
        assert ambiguous

    def test_many_vertices_penalized(self) -> None:
        confidence, ambiguous = _heuristic_confidence(
            "POLYGON((0 0, 0.1 0, 0.2 0, 0.3 0, 0.4 0, 0.5 0, 0.6 0, 0.7 0, "
            "0.8 0, 0.9 0, 1 0, 1 0.1, 1 0.2, 1 0.3, 1 0.4, 1 0.5, 1 0.6, "
            "1 0.7, 1 0.8, 1 0.9, 1 1, 0 1, 0 0))"
        )
        # 23 vertices — should be penalized
        assert confidence < 0.70
        assert ambiguous


class TestValidatePolygon:
    def test_returns_expected_keys(self) -> None:
        result = validate_polygon("POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))")
        assert "confidence_avg" in result
        assert "is_ambiguous" in result
        assert "source" in result
        assert result["source"] == "heuristic"

    def test_confidence_range(self) -> None:
        for geom in [
            "POLYGON((0 0, 1 0, 1 1, 0 1, 0 0))",
            "POLYGON((0 0, 1 0, 1 0.001, 0 0.001, 0 0))",
        ]:
            result = validate_polygon(geom)
            assert 0.0 <= result["confidence_avg"] <= 1.0
