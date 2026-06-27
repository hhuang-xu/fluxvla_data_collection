"""Build dense numpy arrays from configured Parquet columns."""

from __future__ import print_function

import numpy as np


class MissingRequiredColumn(RuntimeError):
    pass


class OptionalFeatureMissing(RuntimeError):
    pass


def build_feature_array(episode, feature):
    arrays = []
    missing = []
    for source in feature.get("sources", []):
        column = source["column"]
        if not episode.has_column(column):
            missing.append(column)
            continue
        arrays.append(_values_to_2d(episode.column_values(column), feature.get("dtype", "float32")))

    if missing:
        message = "feature '{}' missing columns: {}".format(feature["name"], ", ".join(missing))
        if feature.get("required", False):
            raise MissingRequiredColumn(message)
        raise OptionalFeatureMissing(message)

    if not arrays:
        raise OptionalFeatureMissing("feature '{}' has no arrays".format(feature["name"]))

    row_count = arrays[0].shape[0]
    for array in arrays:
        if array.shape[0] != row_count:
            raise ValueError(
                "feature '{}' source row count mismatch: expected {}, got {}".format(
                    feature["name"], row_count, array.shape[0]
                )
            )

    result = np.concatenate(arrays, axis=1).astype(_numpy_dtype(feature.get("dtype", "float32")))
    names = feature.get("names") or []
    if names and len(names) != result.shape[1]:
        raise ValueError(
            "feature '{}' names length {} does not match output dimension {}".format(
                feature["name"], len(names), result.shape[1]
            )
        )
    return result


def _values_to_2d(values, dtype):
    array = np.asarray(values, dtype=_numpy_dtype(dtype))
    if array.ndim == 0:
        array = array.reshape(1, 1)
    elif array.ndim == 1:
        array = array.reshape(-1, 1)
    elif array.ndim > 2:
        array = array.reshape(array.shape[0], -1)
    return array


def _numpy_dtype(dtype):
    if dtype in ("float", "float32"):
        return np.float32
    if dtype == "float64":
        return np.float64
    if dtype in ("int", "int32"):
        return np.int32
    if dtype == "int64":
        return np.int64
    if dtype == "uint8":
        return np.uint8
    if dtype == "uint16":
        return np.uint16
    return np.float32

