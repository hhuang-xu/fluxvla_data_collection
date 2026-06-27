#!/usr/bin/env python3

import argparse
import os
import sys

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE_SRC = os.path.join(PACKAGE_ROOT, "src")
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from fluxvla_data_collection.processing.preprocess import preprocess_dataset
from fluxvla_data_collection.processing.spec import SpecError, load_processing_spec


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert FluxVLA Parquet episodes into processed NPY/MP4 folders."
    )
    parser.add_argument("--raw-root", required=True, help="Root raw_data directory.")
    parser.add_argument("--subfolder", default=None, help="Optional date subfolder, e.g. 20260627.")
    parser.add_argument("--spec", required=True, help="Processing YAML spec.")
    parser.add_argument("--output-root", required=True, help="Processed data output root.")
    parser.add_argument("--output-prefix", default="RealRobot", help="Processed folder prefix.")
    parser.add_argument("--video-codec", default="mp4v", help="OpenCV MP4 codec, e.g. mp4v or h264.")
    parser.add_argument("--task", default=None, help="Fallback task description.")
    parser.add_argument("--overwrite", action="store_true", help="Regenerate existing processed episodes.")
    parser.add_argument(
        "--skip-bad-episodes",
        action="store_true",
        default=True,
        help="Skip bad episodes instead of aborting the whole batch.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Abort on the first bad episode.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print planned work without writing files.")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        spec = load_processing_spec(args.spec)
    except SpecError as exc:
        print("Invalid processing spec: {}".format(exc), file=sys.stderr)
        return 2

    results = preprocess_dataset(
        raw_root=os.path.abspath(args.raw_root),
        output_root=os.path.abspath(args.output_root),
        output_prefix=args.output_prefix,
        spec=spec,
        subfolder=args.subfolder,
        overwrite=args.overwrite,
        skip_bad_episodes=not args.fail_fast,
        dry_run=args.dry_run,
        video_codec=args.video_codec,
        task=args.task,
    )
    status_counts = {}
    for result in results:
        status_counts[result["status"]] = status_counts.get(result["status"], 0) + 1
    print("summary: {}".format(status_counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

