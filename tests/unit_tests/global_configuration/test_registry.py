import pytest

from superset.global_configuration.registry import (
    KEY_MCP_JWT_TTL_SECONDS,
    KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
    deserialize_stored,
    get_default,
    is_public,
    parse_and_validate,
    serialize_value,
)


def test_default_width():
    assert get_default(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX) == 64


def test_parse_valid_width():
    assert parse_and_validate(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX, 128) == 128
    assert parse_and_validate(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX, "96") == 96


@pytest.mark.parametrize("value", [31, 401, "x", None, 12.5])
def test_parse_invalid_width(value):
    with pytest.raises(ValueError):
        parse_and_validate(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX, value)


def test_serialize_int():
    assert serialize_value(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX, 64) == "64"


def test_deserialize_corrupt_int_falls_back_to_default():
    assert (
        deserialize_stored(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX, "not-a-number")
        == get_default(KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX)
    )


def test_default_mcp_jwt_ttl():
    assert get_default(KEY_MCP_JWT_TTL_SECONDS) == 600
    assert is_public(KEY_MCP_JWT_TTL_SECONDS) is False


def test_parse_valid_mcp_jwt_ttl():
    assert parse_and_validate(KEY_MCP_JWT_TTL_SECONDS, 120) == 120
    assert parse_and_validate(KEY_MCP_JWT_TTL_SECONDS, "900") == 900


@pytest.mark.parametrize("value", [59, 3601, "x", None, 12.5])
def test_parse_invalid_mcp_jwt_ttl(value):
    with pytest.raises(ValueError):
        parse_and_validate(KEY_MCP_JWT_TTL_SECONDS, value)
