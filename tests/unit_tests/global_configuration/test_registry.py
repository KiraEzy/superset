import pytest

from superset.global_configuration.registry import (
    KEY_NAVBAR_DISPLAY_NAME_MAX_WIDTH_PX,
    get_default,
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
