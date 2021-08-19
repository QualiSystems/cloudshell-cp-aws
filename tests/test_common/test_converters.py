import pytest

from cloudshell.cp.aws.common.converters import attribute_getter

NAMESPACE = "Resource model"
ATTRIBUTES = {
    f"{NAMESPACE}.name": "resource name",
    f"{NAMESPACE}.is_autoload": "true",
    f"{NAMESPACE}.timeout": "9",
}


@pytest.mark.parametrize(
    ("attr_name", "result", "convert_to_type", "default"),
    (
        ("name", "resource name", None, None),
        ("is_autoload", "true", None, None),
        ("is_autoload", True, bool, None),
        ("timeout", 9, int, None),
        ("missed_arg", "default value", None, "default value"),
        ("missed_arg", 1, bool, "1"),
        ("missed_arg", KeyError, None, None),
        ("name", NotImplementedError, tuple, None),
    ),
)
def test_attribute_getter(attr_name, result, convert_to_type, default):
    get_attr = attribute_getter(ATTRIBUTES, NAMESPACE)
    kwargs = {}
    if convert_to_type is not None:
        kwargs["convert_to_type"] = convert_to_type
    if default is not None:
        kwargs["default"] = default

    if isinstance(result, type) and issubclass(result, Exception):
        with pytest.raises(result):
            get_attr(attr_name, **kwargs)
    else:
        assert get_attr(attr_name, **kwargs) == result
