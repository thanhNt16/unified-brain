from enum import Enum


class ErrorCodes(str, Enum):
    schema_validation = "schema_validation"
    unknown_source = "unknown_source"
    dangling_edge = "dangling_edge"
    unsupported_format = "unsupported_format"
    not_initialized = "not_initialized"
    vault_exists = "vault_exists"
    lock_busy = "lock_busy"
    path_forbidden = "path_forbidden"
    parse_error = "parse_error"
    index_errors = "index_errors"
    db_schema_newer = "db_schema_newer"
    diff_state = "diff_state"
    diff_path = "diff_path"
    limit_error = "limit_error"
    auth_required = "auth_required"
    forbidden = "forbidden"
    not_found = "not_found"
    payload_too_large = "payload_too_large"
    internal_error = "internal_error"


def ok(data: object) -> dict[str, object]:
    return {"ok": True, "data": data}


def error(code: ErrorCodes | str, message: str, details: object | None = None) -> dict[str, object]:
    item: dict[str, object] = {"code": code.value if isinstance(code, ErrorCodes) else code, "message": message}
    if details is not None:
        item["details"] = details
    return {"ok": False, "error": item}
