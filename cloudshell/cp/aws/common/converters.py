from typing import Any, Dict, Optional, Type, Union


def convert_to_bool(value: Union[str, bool]) -> bool:
    if isinstance(value, bool):
        return value
    return value.lower() in ["true", "1"]


def attribute_getter(attributes: Dict[str, Any], namespace: str):
    empty = object()

    def get_attr(
        attr_name: str, convert_to_type: Optional[Type] = None, default: Any = empty
    ) -> Any:
        if default is empty:
            value = attributes[f"{namespace}.{attr_name}"]
        else:
            value = attributes.get(f"{namespace}.{attr_name}", default)

        if convert_to_type is None:
            value = value
        elif convert_to_type is bool:
            value = convert_to_bool(value)
        elif convert_to_type is int:
            value = int(value)
        else:
            raise NotImplementedError(f"Convert to {convert_to_type} is not supported")
        return value

    return get_attr
