"""Computed column converters."""

from fluxvla_data_collection.registry import register_converter


@register_converter("concat")
def concat(values, spec, context):  # noqa: ARG001
    result = []
    for value in values:
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            result.extend(value)
        else:
            result.append(value)
    return {spec["output"]: result}
