from contextlib import suppress


class cached_property:
    def __init__(self, func):
        self.__doc__ = getattr(func, "__doc__")
        self.func = func

    def __get__(self, obj, cls):
        if obj is None:
            return self
        value = obj.__dict__[self.func.__name__] = self.func(obj)
        return value


def invalidated_cache(instance, property_name: str):
    with suppress(KeyError):
        del instance.__dict__[property_name]
