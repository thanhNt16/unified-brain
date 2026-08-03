from kg.envelope import ErrorCodes, error, ok


def test_exact_success_shape() -> None:
    assert ok({"count": 1}) == {"ok": True, "data": {"count": 1}}


def test_exact_error_codes_and_optional_details() -> None:
    assert len(ErrorCodes) == 19
    assert error(ErrorCodes.schema_validation, "bad") == {
        "ok": False,
        "error": {"code": "schema_validation", "message": "bad"},
    }
    assert error("limit_error", "too many", {"limit": 20})["error"]["details"] == {"limit": 20}
