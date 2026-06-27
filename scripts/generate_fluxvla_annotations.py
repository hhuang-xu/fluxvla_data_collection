#!/usr/bin/env python3

import argparse
import os
import sys

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE_SRC = os.path.join(PACKAGE_ROOT, "src")
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from fluxvla_data_collection.processing.annotation import generate_annotations


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate LeRobot annotation json from FluxVLA processed folders."
    )
    parser.add_argument("--processed-root", required=True, help="processed_data root directory.")
    parser.add_argument("--folder-pattern", default="*", help="Glob pattern under processed-root.")
    parser.add_argument("--output", required=True, help="Output annotation json path.")
    parser.add_argument("--task", default=None, help="Override task text for all episodes.")
    parser.add_argument("--video-name", default=None, help="Anchor video name; defaults to info.json primary_video.")
    return parser.parse_args()


def main():
    args = parse_args()
    generate_annotations(
        processed_root=os.path.abspath(args.processed_root),
        folder_pattern=args.folder_pattern,
        output=os.path.abspath(args.output),
        task=args.task,
        video_name=args.video_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

