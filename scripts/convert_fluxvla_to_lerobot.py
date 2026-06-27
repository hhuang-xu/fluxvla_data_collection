#!/usr/bin/env python3

import argparse
import os
import sys

PACKAGE_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PACKAGE_SRC = os.path.join(PACKAGE_ROOT, "src")
if PACKAGE_SRC not in sys.path:
    sys.path.insert(0, PACKAGE_SRC)

from fluxvla_data_collection.processing.lerobot_export import convert_to_lerobot
from fluxvla_data_collection.processing.spec import SpecError, load_processing_spec


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert FluxVLA processed folders into a LeRobot dataset."
    )
    parser.add_argument("--repo-id", required=True, help="LeRobot repo id, e.g. org/dataset.")
    parser.add_argument("--annotation-json", required=True, help="Annotation json path.")
    parser.add_argument("--spec", required=True, help="Processing YAML spec.")
    parser.add_argument("--output-root", required=True, help="LeRobot dataset output root.")
    parser.add_argument("--mode", choices=("video", "image"), default="video")
    parser.add_argument("--fps", type=int, default=None)
    parser.add_argument("--video-codec", default="h264")
    parser.add_argument("--debug", action="store_true", help="Only convert the first two episodes.")
    parser.add_argument("--start-date", default=None, help="Optional YYYYMMDD lower date bound.")
    parser.add_argument("--end-date", default=None, help="Optional YYYYMMDD upper date bound.")
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        spec = load_processing_spec(args.spec)
    except SpecError as exc:
        print("Invalid processing spec: {}".format(exc), file=sys.stderr)
        return 2

    convert_to_lerobot(
        repo_id=args.repo_id,
        annotation_json=os.path.abspath(args.annotation_json),
        spec=spec,
        output_root=os.path.abspath(args.output_root),
        mode=args.mode,
        fps=args.fps,
        video_codec=args.video_codec,
        debug=args.debug,
        start_date=args.start_date,
        end_date=args.end_date,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

