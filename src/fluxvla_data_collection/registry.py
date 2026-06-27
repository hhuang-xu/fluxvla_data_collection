"""Converter registry used by the generic recorder."""

import importlib


_CONVERTERS = {}


class ConverterError(RuntimeError):
    pass


def register_converter(name):
    """Register a converter by name.

    Converter signature:
        converter(value, spec, context) -> dict[column_name, parquet_value]
    """

    def decorator(func):
        if name in _CONVERTERS and _CONVERTERS[name] is not func:
            raise ConverterError("converter '{}' is already registered".format(name))
        _CONVERTERS[name] = func
        return func

    return decorator


def get_converter(name):
    if name in _CONVERTERS:
        return _CONVERTERS[name]
    if ":" in name:
        return load_external_converter(name)
    raise ConverterError("unknown converter '{}'".format(name))


def load_external_converter(path):
    module_name, func_name = path.split(":", 1)
    module = importlib.import_module(module_name)
    func = getattr(module, func_name)
    return func


def list_converters():
    return sorted(_CONVERTERS.keys())
