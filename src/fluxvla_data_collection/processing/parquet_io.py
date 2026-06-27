"""Parquet and sidecar metadata helpers."""

from __future__ import print_function

import json
import os


class EpisodeParquet(object):
    def __init__(self, path, table, meta, footer):
        self.path = path
        self.table = table
        self.meta = meta or {}
        self.footer = footer or {}
        self.columns = set(table.column_names)
        self.num_rows = table.num_rows

    def has_column(self, column):
        return column in self.columns

    def column_values(self, column):
        return self.table.column(column).to_pylist()


def read_episode_parquet(path, columns=None):
    import pyarrow.parquet as pq

    table = pq.read_table(path, columns=columns)
    footer = read_parquet_footer(path)
    meta = read_sidecar_meta(path)
    return EpisodeParquet(path, table, meta, footer)


def read_sidecar_meta(parquet_path):
    meta_path = sidecar_meta_path(parquet_path)
    if not os.path.exists(meta_path):
        return {}
    with open(meta_path, "r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def read_parquet_footer(parquet_path):
    import pyarrow.parquet as pq

    metadata = pq.read_metadata(parquet_path).metadata or {}
    decoded = {}
    for key, value in metadata.items():
        decoded[_decode_meta(key)] = _decode_meta(value)
    return decoded


def sidecar_meta_path(parquet_path):
    if parquet_path.endswith(".parquet"):
        return parquet_path[:-8] + ".meta.json"
    return parquet_path + ".meta.json"


def task_description_for_episode(episode, cli_task=None, fallback=""):
    if episode.meta.get("task_description"):
        return episode.meta["task_description"]
    if episode.footer.get("fluxvla.task_description"):
        return episode.footer["fluxvla.task_description"]
    if cli_task:
        return cli_task
    return fallback


def _decode_meta(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)
