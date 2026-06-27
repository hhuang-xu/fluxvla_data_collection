"""Decode encoded image columns and write MP4 videos."""

from __future__ import print_function

import os

import cv2
import numpy as np


def video_is_readable(path):
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return False
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return False
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    ok, _ = cap.read()
    cap.release()
    return frame_count > 0 and ok


def write_image_bytes_video(path, image_bytes, fps, codec="mp4v", expected_frames=None):
    frames = [_decode_image_bytes(value) for value in image_bytes]
    if expected_frames is not None and len(frames) != expected_frames:
        raise ValueError(
            "video '{}' frame count {} does not match expected {}".format(
                path, len(frames), expected_frames
            )
        )
    return write_video(path, frames, fps, codec)


def write_video(path, frames, fps, codec="mp4v"):
    if not frames:
        raise ValueError("no frames to write: {}".format(path))
    height, width = frames[0].shape[:2]
    writer = _open_video_writer(path, fps, (width, height), codec)
    try:
        for frame in frames:
            if frame is None:
                raise ValueError("decoded empty frame while writing {}".format(path))
            if frame.shape[:2] != (height, width):
                raise ValueError(
                    "frame shape mismatch in '{}': expected {}, got {}".format(
                        path, (height, width), frame.shape[:2]
                    )
                )
            writer.write(frame)
    finally:
        writer.release()
    return {"width": width, "height": height, "frames": len(frames), "path": path}


def _decode_image_bytes(value):
    if value is None:
        raise ValueError("image bytes value is None")
    if isinstance(value, str):
        value = value.encode("latin1")
    if isinstance(value, bytearray):
        value = bytes(value)
    if not isinstance(value, bytes):
        raise TypeError("image column values must be bytes, got {}".format(type(value)))
    buffer = np.frombuffer(value, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("failed to decode image bytes")
    return image


def _open_video_writer(path, fps, frame_size, codec):
    for candidate in _codec_candidates(codec):
        fourcc = cv2.VideoWriter_fourcc(*candidate)
        writer = cv2.VideoWriter(path, fourcc, float(fps), frame_size)
        if writer.isOpened():
            return writer
        writer.release()
    raise RuntimeError("failed to open video writer: {}".format(path))


def _codec_candidates(codec):
    lowered = codec.lower()
    if lowered in ("h264", "avc1"):
        return ["avc1", "H264", "X264", "mp4v"]
    if lowered == "mp4v":
        return ["mp4v"]
    return [codec, "mp4v"]

