from __future__ import annotations

import math
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cv2
import mediapipe as mp
import numpy as np
from PIL import Image, ImageDraw, ImageFont


ProgressCallback = Callable[[int, str], None]


class AnalysisError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class PoseFrame:
    frame_index: int
    timestamp: float
    landmarks: np.ndarray
    quality: float


POSE = mp.solutions.pose.PoseLandmark
CORE_LANDMARKS = [
    POSE.LEFT_SHOULDER.value,
    POSE.RIGHT_SHOULDER.value,
    POSE.LEFT_HIP.value,
    POSE.RIGHT_HIP.value,
    POSE.LEFT_KNEE.value,
    POSE.RIGHT_KNEE.value,
    POSE.LEFT_ANKLE.value,
    POSE.RIGHT_ANKLE.value,
]


def _point(landmarks: np.ndarray, landmark: POSE) -> np.ndarray:
    return landmarks[landmark.value, :2]


def _midpoint(landmarks: np.ndarray, left: POSE, right: POSE) -> np.ndarray:
    return (_point(landmarks, left) + _point(landmarks, right)) / 2.0


def _distance(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def _angle(a: np.ndarray, b: np.ndarray, c: np.ndarray) -> float:
    ba = a - b
    bc = c - b
    denominator = float(np.linalg.norm(ba) * np.linalg.norm(bc))
    if denominator < 1e-6:
        return 0.0
    cosine = float(np.clip(np.dot(ba, bc) / denominator, -1.0, 1.0))
    return math.degrees(math.acos(cosine))


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def _body_axis_angle_from_horizontal(pose_frames: list[PoseFrame]) -> float:
    angles: list[float] = []
    for item in pose_frames:
        shoulder = _midpoint(item.landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        ankle = _midpoint(item.landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE)
        vector = ankle - shoulder
        angles.append(abs(math.degrees(math.atan2(float(vector[1]), float(vector[0])))) % 180)
    normalized = [min(angle, 180 - angle) for angle in angles]
    return float(np.median(normalized))


def _format_timestamp(seconds: float) -> str:
    minutes = int(seconds // 60)
    remainder = int(round(seconds % 60))
    if remainder == 60:
        minutes += 1
        remainder = 0
    return f"{minutes:02d}:{remainder:02d}"


def _timestamp_seconds(value: str) -> float:
    minutes, seconds = value.split(":", 1)
    return int(minutes) * 60 + int(seconds)


def _video_metadata(path: Path) -> tuple[cv2.VideoCapture, float, int, int, int, float]:
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise AnalysisError("VIDEO_OPEN_FAILED", "无法打开视频，请确认文件没有损坏。")

    fps = float(capture.get(cv2.CAP_PROP_FPS))
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
        capture.release()
        raise AnalysisError("VIDEO_METADATA_INVALID", "无法读取视频帧率或画面尺寸。")

    duration = frame_count / fps
    if duration < 10 or duration > 180:
        capture.release()
        raise AnalysisError("VIDEO_DURATION_INVALID", "请选择 10 秒至 3 分钟的视频。")
    return capture, fps, frame_count, width, height, duration


def _default_sample_fps(duration: float) -> float:
    """按时长自适应的目标采样帧率（越长的视频抽得越稀，兼顾精度与耗时）。"""
    return 10.0 if duration <= 30 else 8.0 if duration <= 60 else 5.0


def _extract_pose_frames(
    path: Path,
    progress: ProgressCallback,
    sample_fps_override: float | None = None,
) -> tuple[list[PoseFrame], dict[str, float]]:
    capture, fps, frame_count, width, height, duration = _video_metadata(path)
    capture.release()
    target_sample_fps = min(sample_fps_override or _default_sample_fps(duration), fps)
    sample_count = min(600, max(40, int(math.ceil(duration * target_sample_fps))))
    indices = np.unique(np.linspace(0, frame_count - 1, sample_count, dtype=np.int32))
    pose_frames: list[PoseFrame] = []

    started_at = time.perf_counter()
    progress(12, "并行读取动作片段")
    worker_count = 2 if len(indices) >= 120 else 1
    chunks = [chunk for chunk in np.array_split(indices, worker_count) if len(chunk)]
    processed = 0
    progress_lock = threading.Lock()

    def process_chunk(chunk: np.ndarray) -> list[PoseFrame]:
        nonlocal processed
        local_capture = cv2.VideoCapture(str(path))
        local_capture.set(cv2.CAP_PROP_POS_FRAMES, int(chunk[0]))
        results: list[PoseFrame] = []
        position = 0
        current_index = int(chunk[0])
        with mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.4,
            min_tracking_confidence=0.4,
        ) as pose:
            while position < len(chunk) and current_index <= int(chunk[-1]):
                ok = local_capture.grab()
                if not ok:
                    break
                if current_index == int(chunk[position]):
                    ok, frame = local_capture.retrieve()
                    if ok:
                        inference_frame = frame
                        longest_side = max(frame.shape[:2])
                        if longest_side > 640:
                            scale = 640 / longest_side
                            inference_frame = cv2.resize(frame, (int(frame.shape[1] * scale), int(frame.shape[0] * scale)), interpolation=cv2.INTER_AREA)
                        result = pose.process(cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB))
                        if result.pose_landmarks:
                            landmarks = np.array([[item.x, item.y, item.z, item.visibility] for item in result.pose_landmarks.landmark], dtype=np.float32)
                            quality = float(np.mean(landmarks[CORE_LANDMARKS, 3]))
                            if quality >= 0.32:
                                results.append(PoseFrame(int(current_index), float(current_index / fps), landmarks, quality))
                    position += 1
                    with progress_lock:
                        processed += 1
                        if processed == len(indices) or processed % 12 == 0:
                            progress(18 + int(55 * processed / len(indices)), "并行跟踪身体关键点")
                current_index += 1
        local_capture.release()
        return results

    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="pose") as executor:
        futures = [executor.submit(process_chunk, chunk) for chunk in chunks]
        for future in as_completed(futures):
            pose_frames.extend(future.result())
    pose_frames.sort(key=lambda item: item.frame_index)
    detection_ratio = len(pose_frames) / max(1, len(indices))
    if len(pose_frames) < 4 or detection_ratio < 0.15:
        raise AnalysisError(
            "POSE_NOT_DETECTED",
            "无法稳定识别身体关键点。请使用固定机位，确保全身入镜且光线充足。",
        )

    average_quality = float(np.mean([item.quality for item in pose_frames]))
    confidence = _clamp(100 * average_quality * min(1.0, detection_ratio / 0.7))
    metadata = {
        "fps": fps,
        "frameCount": frame_count,
        "width": width,
        "height": height,
        "durationSeconds": duration,
        "sampledFrames": len(indices),
        "sampleRateFps": len(indices) / duration,
        "targetSampleFps": target_sample_fps,
        "detectedFrames": len(pose_frames),
        "detectionRatio": detection_ratio,
        "confidence": confidence,
        "analysisSeconds": time.perf_counter() - started_at,
        "inferenceMaxSide": 640,
        "analysisWorkers": worker_count,
        "maxSampleFrames": 600,
    }
    return pose_frames, metadata


def _pick_distinct_frame(
    ranked: list[tuple[float, PoseFrame, int, float]],
    selected: list[PoseFrame],
) -> tuple[PoseFrame, int, float]:
    for _, frame, side, value in ranked:
        if all(abs(frame.timestamp - existing.timestamp) >= 0.75 for existing in selected):
            selected.append(frame)
            return frame, side, value
    for _, frame, side, value in ranked:
        if all(frame.frame_index != existing.frame_index for existing in selected):
            selected.append(frame)
            return frame, side, value
    _, frame, side, value = ranked[0]
    selected.append(frame)
    return frame, side, value


def _running_measurements(pose_frames: list[PoseFrame]) -> tuple[dict[str, float], dict[str, tuple[PoseFrame, int, float]]]:
    torso_leans: list[float] = []
    knee_differences: list[float] = []
    arm_differences: list[float] = []
    ankle_offsets: list[float] = []
    landing_candidates: list[tuple[float, PoseFrame, int, float]] = []
    posture_candidates: list[tuple[float, PoseFrame, int, float]] = []
    symmetry_candidates: list[tuple[float, PoseFrame, int, float]] = []
    arm_candidates: list[tuple[float, PoseFrame, int, float]] = []

    for item in pose_frames:
        landmarks = item.landmarks
        mid_shoulder = _midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        mid_hip = _midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP)
        mid_ankle = _midpoint(landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE)
        body_height = max(0.08, _distance(mid_shoulder, mid_hip) + _distance(mid_hip, mid_ankle))

        torso_vector = mid_shoulder - mid_hip
        torso_lean = abs(math.degrees(math.atan2(float(torso_vector[0]), float(-torso_vector[1]))))
        torso_leans.append(torso_lean)

        left_knee = _angle(
            _point(landmarks, POSE.LEFT_HIP),
            _point(landmarks, POSE.LEFT_KNEE),
            _point(landmarks, POSE.LEFT_ANKLE),
        )
        right_knee = _angle(
            _point(landmarks, POSE.RIGHT_HIP),
            _point(landmarks, POSE.RIGHT_KNEE),
            _point(landmarks, POSE.RIGHT_ANKLE),
        )
        knee_difference = abs(left_knee - right_knee)
        knee_differences.append(knee_difference)

        left_elbow = _angle(
            _point(landmarks, POSE.LEFT_SHOULDER),
            _point(landmarks, POSE.LEFT_ELBOW),
            _point(landmarks, POSE.LEFT_WRIST),
        )
        right_elbow = _angle(
            _point(landmarks, POSE.RIGHT_SHOULDER),
            _point(landmarks, POSE.RIGHT_ELBOW),
            _point(landmarks, POSE.RIGHT_WRIST),
        )
        arm_difference = abs(left_elbow - right_elbow)
        arm_differences.append(arm_difference)

        side_offsets = []
        for hip, ankle, side in [
            (POSE.LEFT_HIP, POSE.LEFT_ANKLE, 0),
            (POSE.RIGHT_HIP, POSE.RIGHT_ANKLE, 1),
        ]:
            offset = abs(float(_point(landmarks, ankle)[0] - _point(landmarks, hip)[0])) / body_height
            side_offsets.append((offset, side))
        frame_offset, side = max(side_offsets)
        ankle_offsets.append(frame_offset)
        landing_candidates.append((frame_offset, item, side, frame_offset))
        posture_candidates.append((abs(torso_lean - 8.0), item, 0, torso_lean))
        symmetry_candidates.append((knee_difference, item, 0, knee_difference))
        arm_candidates.append((arm_difference, item, 0, arm_difference))

    lean = float(np.median(torso_leans))
    lean_stability = float(np.std(torso_leans))
    knee_difference = float(np.median(knee_differences))
    ankle_offset = float(np.percentile(ankle_offsets, 85))
    arm_difference = float(np.median(arm_differences))
    selected: list[PoseFrame] = []
    evidences = {
        "A": _pick_distinct_frame(sorted(landing_candidates, reverse=True, key=lambda value: value[0]), selected),
        "B": _pick_distinct_frame(sorted(posture_candidates, reverse=True, key=lambda value: value[0]), selected),
        "C": _pick_distinct_frame(sorted(symmetry_candidates, reverse=True, key=lambda value: value[0]), selected),
        "D": _pick_distinct_frame(sorted(arm_candidates, reverse=True, key=lambda value: value[0]), selected),
    }
    values = {
        "torsoLean": lean,
        "torsoLeanStd": lean_stability,
        "kneeDifference": knee_difference,
        "ankleOffsetRatio": ankle_offset,
        "armDifference": arm_difference,
    }
    return values, evidences


def _landmark_visibility(item: PoseFrame, landmarks: list[POSE]) -> float:
    return float(np.mean([item.landmarks[landmark.value, 3] for landmark in landmarks]))


def _episode_count(samples: list[tuple[float, PoseFrame]], threshold: float, gap_seconds: float = 0.65) -> int:
    timestamps = [frame.timestamp for value, frame in samples if value >= threshold]
    if not timestamps:
        return 0
    count = 1
    for previous, current in zip(timestamps, timestamps[1:]):
        if current - previous > gap_seconds:
            count += 1
    return count


SWIM_STROKE_NAMES = {
    "freestyle": "自由泳",
    "breaststroke": "蛙泳",
    "backstroke": "仰泳",
    "butterfly": "蝶泳",
    "unknown": "泳姿待确认",
}


def _safe_correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 8 or len(right) < 8 or np.std(left) < 1e-4 or np.std(right) < 1e-4:
        return 0.0
    return float(np.clip(np.corrcoef(left, right)[0, 1], -1.0, 1.0))


def _classify_swim_stroke(pose_frames: list[PoseFrame]) -> dict[str, object]:
    left_reach: list[float] = []
    right_reach: list[float] = []
    left_knee: list[float] = []
    right_knee: list[float] = []
    face_sides: list[float] = []

    for item in pose_frames:
        landmarks = item.landmarks
        shoulder = _midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        hip = _midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP)
        torso = max(0.04, _distance(shoulder, hip))
        axis = shoulder - hip
        axis /= max(1e-6, float(np.linalg.norm(axis)))
        perpendicular = np.array([-axis[1], axis[0]], dtype=np.float32)
        if _landmark_visibility(item, [POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER, POSE.LEFT_WRIST, POSE.RIGHT_WRIST]) >= 0.48:
            left_reach.append(float(np.dot(_point(landmarks, POSE.LEFT_WRIST) - shoulder, axis)) / torso)
            right_reach.append(float(np.dot(_point(landmarks, POSE.RIGHT_WRIST) - shoulder, axis)) / torso)
        if _landmark_visibility(item, [POSE.LEFT_HIP, POSE.RIGHT_HIP, POSE.LEFT_KNEE, POSE.RIGHT_KNEE, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE]) >= 0.48:
            left_knee.append(180.0 - _angle(_point(landmarks, POSE.LEFT_HIP), _point(landmarks, POSE.LEFT_KNEE), _point(landmarks, POSE.LEFT_ANKLE)))
            right_knee.append(180.0 - _angle(_point(landmarks, POSE.RIGHT_HIP), _point(landmarks, POSE.RIGHT_KNEE), _point(landmarks, POSE.RIGHT_ANKLE)))
        if _landmark_visibility(item, [POSE.NOSE, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER]) >= 0.48:
            face_sides.append(float(np.dot(_point(landmarks, POSE.NOSE) - shoulder, perpendicular)) / torso)

    arm_sync = _safe_correlation(left_reach, right_reach)
    leg_sync = _safe_correlation(left_knee, right_knee)
    knee_flexion = float(np.percentile(left_knee + right_knee, 75)) if left_knee or right_knee else 0.0
    face_side = float(np.median(face_sides)) if face_sides else 0.0
    coverage = min(1.0, len(left_reach) / 40.0)
    arm_motion = float(np.std(left_reach) + np.std(right_reach)) if left_reach and right_reach else 0.0

    # Alternating arms indicate crawl/backstroke; synchronous arms separate breaststroke/butterfly.
    scores = {
        "freestyle": 0.45 + max(0.0, -arm_sync) * 0.4 + max(0.0, face_side) * 0.08,
        "backstroke": 0.36 + max(0.0, -arm_sync) * 0.34 + max(0.0, -face_side) * 0.16,
        "breaststroke": 0.20 + max(0.0, arm_sync) * 0.4 + max(0.0, leg_sync) * 0.08 + min(0.16, knee_flexion / 360.0),
        "butterfly": 0.22 + max(0.0, arm_sync) * 0.46 + max(0.0, leg_sync) * 0.08 + max(0.0, 45.0 - knee_flexion) / 360.0,
    }
    if arm_sync < 0.25:
        scores["breaststroke"] = min(scores["breaststroke"], 0.38)
        scores["butterfly"] = min(scores["butterfly"], 0.38)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best_stroke, best_score = ranked[0]
    margin = best_score - ranked[1][1]
    confidence = float(np.clip((0.48 + margin) * coverage * 100.0, 0.0, 95.0))
    if arm_motion < 0.12:
        confidence = min(confidence, 35.0)
    stroke = best_stroke if confidence >= 48 else "unknown"
    return {
        "stroke": stroke,
        "strokeName": SWIM_STROKE_NAMES[stroke],
        "confidence": round(confidence),
        "candidates": [{"stroke": key, "name": SWIM_STROKE_NAMES[key], "score": round(value, 3)} for key, value in ranked[:2]],
        "signals": {"armSynchrony": round(arm_sync, 3), "legSynchrony": round(leg_sync, 3), "armMotion": round(arm_motion, 3), "sampleCoverage": round(coverage, 3)},
    }


def _swimming_measurements(pose_frames: list[PoseFrame]) -> tuple[dict[str, float], dict[str, tuple[PoseFrame, int, float]]]:
    head_samples: list[tuple[float, PoseFrame]] = []
    body_samples: list[tuple[float, PoseFrame]] = []
    kick_samples: list[tuple[float, PoseFrame]] = []
    arm_samples: dict[int, list[tuple[float, float, PoseFrame]]] = {0: [], 1: []}

    head_candidates: list[tuple[float, PoseFrame, int, float]] = []
    body_candidates: list[tuple[float, PoseFrame, int, float]] = []
    kick_candidates: list[tuple[float, PoseFrame, int, float]] = []

    for item in pose_frames:
        landmarks = item.landmarks
        mid_shoulder = _midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        mid_hip = _midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP)
        mid_ankle = _midpoint(landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE)
        torso_length = max(0.04, _distance(mid_shoulder, mid_hip))
        body_axis = mid_shoulder - mid_hip
        body_axis /= max(1e-6, float(np.linalg.norm(body_axis)))
        perpendicular = np.array([-body_axis[1], body_axis[0]], dtype=np.float32)

        if _landmark_visibility(item, [POSE.NOSE, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER]) >= 0.48:
            nose = _point(landmarks, POSE.NOSE)
            head_deviation = abs(float(np.dot(nose - mid_shoulder, perpendicular))) / torso_length
            head_samples.append((head_deviation, item))
            head_candidates.append((head_deviation, item, 0, head_deviation))

        if _landmark_visibility(item, [POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER, POSE.LEFT_HIP, POSE.RIGHT_HIP, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE]) >= 0.48:
            body_slope = abs(math.degrees(math.atan2(float(mid_ankle[1] - mid_shoulder[1]), float(mid_ankle[0] - mid_shoulder[0]))))
            body_slope = min(body_slope, 180.0 - body_slope)
            body_bend = abs(180.0 - _angle(mid_shoulder, mid_hip, mid_ankle))
            body_issue = max(body_slope, body_bend)
            body_samples.append((body_issue, item))
            body_candidates.append((body_issue, item, 0, body_issue))

        for side, shoulder_landmark, elbow_landmark, wrist_landmark in [
            (0, POSE.LEFT_SHOULDER, POSE.LEFT_ELBOW, POSE.LEFT_WRIST),
            (1, POSE.RIGHT_SHOULDER, POSE.RIGHT_ELBOW, POSE.RIGHT_WRIST),
        ]:
            if _landmark_visibility(item, [shoulder_landmark, elbow_landmark, wrist_landmark]) < 0.5:
                continue
            shoulder = _point(landmarks, shoulder_landmark)
            wrist = _point(landmarks, wrist_landmark)
            extension = float(np.dot(wrist - shoulder, body_axis)) / torso_length
            downward_drop = abs(float(np.dot(wrist - shoulder, perpendicular))) / torso_length
            arm_samples[side].append((extension, downward_drop, item))

        if _landmark_visibility(item, [POSE.LEFT_HIP, POSE.RIGHT_HIP, POSE.LEFT_KNEE, POSE.RIGHT_KNEE, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE]) >= 0.48:
            left_knee = _angle(_point(landmarks, POSE.LEFT_HIP), _point(landmarks, POSE.LEFT_KNEE), _point(landmarks, POSE.LEFT_ANKLE))
            right_knee = _angle(_point(landmarks, POSE.RIGHT_HIP), _point(landmarks, POSE.RIGHT_KNEE), _point(landmarks, POSE.RIGHT_ANKLE))
            knee_flexion = max(180.0 - left_knee, 180.0 - right_knee)
            kick_samples.append((knee_flexion, item))
            kick_candidates.append((knee_flexion, item, 0, knee_flexion))

    reach_candidates: list[tuple[float, PoseFrame, int, float]] = []
    reach_events: list[tuple[float, PoseFrame]] = []
    for side, samples in arm_samples.items():
        last_event_time = -10.0
        for index in range(1, len(samples) - 1):
            previous, current, following = samples[index - 1], samples[index], samples[index + 1]
            extension, drop, frame = current
            if extension >= previous[0] and extension >= following[0] and extension > 0.25 and frame.timestamp - last_event_time >= 0.7:
                reach_candidates.append((drop, frame, side, drop))
                reach_events.append((drop, frame))
                last_event_time = frame.timestamp

    fallback_frame = max(pose_frames, key=lambda item: item.quality)
    if not head_candidates:
        head_candidates = [(0.0, fallback_frame, 0, 0.0)]
    if not body_candidates:
        body_candidates = [(0.0, fallback_frame, 0, 0.0)]
    if not reach_candidates:
        best_arm = max(
            ((drop, frame, side, drop) for side, samples in arm_samples.items() for _, drop, frame in samples),
            default=(0.0, fallback_frame, 0, 0.0),
            key=lambda value: value[0],
        )
        reach_candidates = [best_arm]
    if not kick_candidates:
        kick_candidates = [(0.0, fallback_frame, 0, 0.0)]

    selected: list[PoseFrame] = []
    evidences = {
        "A": _pick_distinct_frame(sorted(head_candidates, reverse=True, key=lambda value: value[0]), selected),
        "B": _pick_distinct_frame(sorted(body_candidates, reverse=True, key=lambda value: value[0]), selected),
        "C": _pick_distinct_frame(sorted(reach_candidates, reverse=True, key=lambda value: value[0]), selected),
        "D": _pick_distinct_frame(sorted(kick_candidates, reverse=True, key=lambda value: value[0]), selected),
    }
    values = {
        "headDeviation": float(np.percentile([value for value, _ in head_samples], 85)) if head_samples else 0.0,
        "bodyIssue": float(np.percentile([value for value, _ in body_samples], 75)) if body_samples else 0.0,
        "frontArmDrop": float(np.percentile([value for value, _ in reach_events], 75)) if reach_events else evidences["C"][2],
        "kneeFlexion": float(np.percentile([value for value, _ in kick_samples], 75)) if kick_samples else 0.0,
        "headEpisodes": float(_episode_count(head_samples, 0.36)),
        "bodyEpisodes": float(_episode_count(body_samples, 14.0)),
        "reachEvents": float(len(reach_events)),
        "kickEpisodes": float(_episode_count(kick_samples, 38.0)),
        "headSamples": float(len(head_samples)),
        "bodySamples": float(len(body_samples)),
        "kickSamples": float(len(kick_samples)),
    }
    return values, evidences


def _pixel(point: np.ndarray, width: int, height: int) -> tuple[int, int]:
    return int(np.clip(point[0], 0, 1) * width), int(np.clip(point[1], 0, 1) * height)


def _draw_dashed_line(
    image: np.ndarray,
    start: tuple[int, int],
    end: tuple[int, int],
    color: tuple[int, int, int],
    thickness: int = 2,
    dash: int = 10,
) -> None:
    vector = np.array(end, dtype=float) - np.array(start, dtype=float)
    length = float(np.linalg.norm(vector))
    if length < 1:
        return
    direction = vector / length
    for offset in np.arange(0, length, dash * 2):
        segment_start = np.array(start, dtype=float) + direction * offset
        segment_end = np.array(start, dtype=float) + direction * min(offset + dash, length)
        cv2.line(image, tuple(segment_start.astype(int)), tuple(segment_end.astype(int)), color, thickness, cv2.LINE_AA)


def _chinese_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("/System/Library/Fonts/STHeiti Medium.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _draw_chinese_label(
    image: np.ndarray,
    text: str,
    origin: tuple[int, int],
    size: int,
    accent_bgr: tuple[int, int, int],
) -> np.ndarray:
    canvas = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(canvas)
    font = _chinese_font(size)
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    text_width = right - left
    text_height = bottom - top
    x = max(12, min(origin[0], image.shape[1] - text_width - 28))
    y = max(12, min(origin[1], image.shape[0] - text_height - 28))
    accent_rgb = tuple(reversed(accent_bgr))
    draw.rounded_rectangle(
        (x - 10, y - 8, x + text_width + 10, y + text_height + 10),
        radius=6,
        fill=(15, 18, 17),
        outline=accent_rgb,
        width=3,
    )
    draw.text((x, y - top), text, font=font, fill=(248, 250, 249))
    return cv2.cvtColor(np.asarray(canvas), cv2.COLOR_RGB2BGR)


def _evidence_accent(sport: str, marker: str, measurement: float) -> tuple[int, int, int]:
    red = (45, 55, 235)
    yellow = (0, 220, 255)
    green = (90, 190, 40)
    if sport == "running":
        concerning = measurement > 0.3 if marker == "A" else abs(measurement - 8) > 8 if marker == "B" else measurement >= 10 if marker == "C" else measurement >= 15
    else:
        concerning = measurement >= 0.36 if marker == "A" else measurement >= 14 if marker == "B" else measurement >= 0.28 if marker == "C" else measurement >= 38
    if not concerning:
        return green
    return red if marker == "A" else yellow


def _draw_focus_callout(
    image: np.ndarray,
    points: list[tuple[int, int]],
    color: tuple[int, int, int],
    arrow_start: tuple[int, int],
) -> None:
    coordinates = np.array(points, dtype=np.int32)
    x, y, width, height = cv2.boundingRect(coordinates)
    padding = max(22, image.shape[1] // 45)
    center = (x + width // 2, y + height // 2)
    axes = (max(34, width // 2 + padding), max(28, height // 2 + padding))
    cv2.ellipse(image, center, axes, 0, 0, 360, color, max(3, image.shape[1] // 360), cv2.LINE_AA)
    cv2.arrowedLine(image, arrow_start, center, color, max(3, image.shape[1] // 360), cv2.LINE_AA, tipLength=0.08)


def _callout_origin(image: np.ndarray, points: list[tuple[int, int]]) -> tuple[int, int]:
    center_x = sum(point[0] for point in points) / len(points)
    center_y = sum(point[1] for point in points) / len(points)
    x = int(image.shape[1] * 0.58) if center_x < image.shape[1] * 0.5 else 24
    y = 72 if center_y > image.shape[0] * 0.45 else image.shape[0] - max(88, image.shape[0] // 9)
    return x, y


def _render_evidence(
    video_path: Path,
    item: PoseFrame,
    sport: str,
    marker: str,
    side: int,
    measurement: float,
    output_path: Path,
    swim_stroke: str = "freestyle",
) -> None:
    capture = cv2.VideoCapture(str(video_path))
    capture.set(cv2.CAP_PROP_POS_FRAMES, item.frame_index)
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise AnalysisError("EVIDENCE_FRAME_READ_FAILED", "无法重新读取证据帧。")
    height, width = image.shape[:2]
    if width > 1280:
        scale = 1280 / width
        image = cv2.resize(image, (1280, int(height * scale)), interpolation=cv2.INTER_AREA)
        height, width = image.shape[:2]

    landmarks = item.landmarks
    actual_blue = (255, 196, 92)
    target_green = (90, 190, 40)
    white = (236, 242, 239)
    radius = max(5, width // 180)

    label = ""
    label_origin = (24, height - max(64, height // 10))
    focus_points: list[tuple[int, int]] = []
    if sport == "running" and marker == "A":
        hip_landmark = POSE.LEFT_HIP if side == 0 else POSE.RIGHT_HIP
        ankle_landmark = POSE.LEFT_ANKLE if side == 0 else POSE.RIGHT_ANKLE
        hip = _pixel(_point(landmarks, hip_landmark), width, height)
        ankle = _pixel(_point(landmarks, ankle_landmark), width, height)
        knee_landmark = POSE.LEFT_KNEE if side == 0 else POSE.RIGHT_KNEE
        knee = _pixel(_point(landmarks, knee_landmark), width, height)
        projected = (hip[0], ankle[1])
        _draw_dashed_line(image, hip, projected, white, max(1, width // 600), max(7, width // 100))
        cv2.arrowedLine(image, projected, ankle, actual_blue, max(2, width // 420), cv2.LINE_AA, tipLength=0.08)
        cv2.circle(image, hip, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, ankle, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, projected, radius + 2, target_green, max(2, width // 500), cv2.LINE_AA)
        label = "脚落得离身体太远" if measurement > 0.3 else "落点接近身体"
        label_origin = (min(projected[0], ankle[0]), ankle[1] - max(54, height // 12))
        focus_points = [knee, ankle]
    elif sport == "running" and marker == "B":
        shoulder = _pixel(_midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER), width, height)
        hip = _pixel(_midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP), width, height)
        reference = (hip[0], max(8, hip[1] - int(_distance(np.array(shoulder), np.array(hip)))))
        _draw_dashed_line(image, hip, reference, white, max(1, width // 600), max(7, width // 100))
        cv2.line(image, hip, shoulder, actual_blue, max(2, width // 420), cv2.LINE_AA)
        cv2.circle(image, shoulder, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, hip, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, reference, radius + 2, target_green, max(2, width // 500), cv2.LINE_AA)
        label = "上半身压得太低" if measurement > 16 else "身体过于直立" if measurement < 3 else "上半身角度自然"
        label_origin = (min(shoulder[0], hip[0]), max(shoulder[1], hip[1]) + 20)
        focus_points = [shoulder, hip]
    elif sport == "running" and marker == "C":
        for hip_landmark, knee_landmark, ankle_landmark in [
            (POSE.LEFT_HIP, POSE.LEFT_KNEE, POSE.LEFT_ANKLE),
            (POSE.RIGHT_HIP, POSE.RIGHT_KNEE, POSE.RIGHT_ANKLE),
        ]:
            points = [_pixel(_point(landmarks, landmark), width, height) for landmark in (hip_landmark, knee_landmark, ankle_landmark)]
            cv2.polylines(image, [np.array(points, dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
            for point in points:
                cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
            focus_points.extend(points)
        label = "两条腿弯曲幅度不同" if measurement >= 10 else "两条腿动作接近"
    elif sport == "running":
        for shoulder_landmark, elbow_landmark, wrist_landmark in [
            (POSE.LEFT_SHOULDER, POSE.LEFT_ELBOW, POSE.LEFT_WRIST),
            (POSE.RIGHT_SHOULDER, POSE.RIGHT_ELBOW, POSE.RIGHT_WRIST),
        ]:
            points = [_pixel(_point(landmarks, landmark), width, height) for landmark in (shoulder_landmark, elbow_landmark, wrist_landmark)]
            cv2.polylines(image, [np.array(points, dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
            for point in points:
                cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
            focus_points.extend(points)
        label = "两只手臂摆动不同步" if measurement >= 15 else "两侧摆臂节奏接近"
    elif marker == "A":
        nose = _pixel(_point(landmarks, POSE.NOSE), width, height)
        shoulder = _pixel(_midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER), width, height)
        hip = _pixel(_midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP), width, height)
        cv2.line(image, hip, shoulder, target_green, max(2, width // 500), cv2.LINE_AA)
        cv2.line(image, shoulder, nose, actual_blue, max(2, width // 420), cv2.LINE_AA)
        cv2.circle(image, nose, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, shoulder, radius, target_green, -1, cv2.LINE_AA)
        label = "头部偏离身体前进方向" if measurement >= 0.36 else "头部顺着身体向前延伸"
        focus_points = [nose, shoulder]
    elif marker == "B":
        shoulder = _pixel(_midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER), width, height)
        hip = _pixel(_midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP), width, height)
        ankle = _pixel(_midpoint(landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE), width, height)
        cv2.polylines(image, [np.array([shoulder, hip, ankle], dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
        _draw_dashed_line(image, shoulder, ankle, target_green, max(2, width // 500), max(7, width // 100))
        for point in (shoulder, hip, ankle):
            cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
        label = "身体中段有明显下沉" if measurement >= 8 else "身体线比较稳定"
        focus_points = [shoulder, hip, ankle]
    elif marker == "C":
        shoulder_landmark, elbow_landmark, wrist_landmark = (
            (POSE.LEFT_SHOULDER, POSE.LEFT_ELBOW, POSE.LEFT_WRIST)
            if side == 0
            else (POSE.RIGHT_SHOULDER, POSE.RIGHT_ELBOW, POSE.RIGHT_WRIST)
        )
        points = [_pixel(_point(landmarks, landmark), width, height) for landmark in (shoulder_landmark, elbow_landmark, wrist_landmark)]
        cv2.polylines(image, [np.array(points, dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
        cv2.line(image, points[0], points[2], target_green, max(2, width // 500), cv2.LINE_AA)
        for point in points:
            cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
        focus_points = points
        stroke_labels = {
            "freestyle": ("前手还没伸长就向下压", "前手先向前伸长再抓水"),
            "backstroke": ("手臂入水方向偏离肩线", "手臂沿肩线方向入水"),
            "breaststroke": ("双手前伸方向不够稳定", "双手向前伸直后再滑行"),
            "butterfly": ("手臂入水后过早下压", "双臂入水后先向前延伸"),
            "unknown": ("手臂路径需要更多证据", "手臂路径需要更多证据"),
        }
        issue_label, good_label = stroke_labels.get(swim_stroke, stroke_labels["unknown"])
        label = issue_label if measurement >= 0.28 else good_label
    else:
        for hip_landmark, knee_landmark, ankle_landmark in [
            (POSE.LEFT_HIP, POSE.LEFT_KNEE, POSE.LEFT_ANKLE),
            (POSE.RIGHT_HIP, POSE.RIGHT_KNEE, POSE.RIGHT_ANKLE),
        ]:
            points = [_pixel(_point(landmarks, landmark), width, height) for landmark in (hip_landmark, knee_landmark, ankle_landmark)]
            cv2.polylines(image, [np.array(points, dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
            for point in points:
                cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
            focus_points.extend(points)
        target_hip = _pixel(_midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP), width, height)
        target_ankle = _pixel(_midpoint(landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE), width, height)
        _draw_dashed_line(image, target_hip, target_ankle, target_green, max(2, width // 500), max(7, width // 100))
        kick_labels = {
            "freestyle": ("打腿时膝盖弯得太多", "打腿幅度比较轻松"),
            "backstroke": ("打腿时膝盖折起较多", "腿部连续向上踢水"),
            "breaststroke": ("收腿时膝盖幅度偏大", "收腿后双脚向后蹬夹"),
            "butterfly": ("海豚腿在膝盖处折得较多", "波浪由躯干带到双腿"),
            "unknown": ("腿部动作需要更多证据", "腿部动作需要更多证据"),
        }
        issue_label, good_label = kick_labels.get(swim_stroke, kick_labels["unknown"])
        label = issue_label if measurement >= 38 else good_label

    font_size = max(20, width // 42)
    accent = _evidence_accent(sport, marker, measurement)
    if focus_points:
        label_origin = _callout_origin(image, focus_points)
        _draw_focus_callout(image, focus_points, accent, label_origin)
    image = _draw_chinese_label(image, label, label_origin, font_size, accent)
    image = _draw_chinese_label(image, f"证据 {marker} · {_format_timestamp(item.timestamp)}", (18, 16), max(17, width // 52), accent)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(output_path), image, [cv2.IMWRITE_JPEG_QUALITY, 90]):
        raise AnalysisError("EVIDENCE_WRITE_FAILED", "无法生成证据帧。")


def _render_evidence_set(
    video_path: Path,
    sport: str,
    evidences: dict[str, tuple[PoseFrame, int, float]],
    output_path: Path,
    media_url: str,
    swim_stroke: str = "freestyle",
) -> dict[str, str]:
    media_root = media_url.rsplit("/", 1)[0]
    def render(item: tuple[str, tuple[PoseFrame, int, float]]) -> tuple[str, str]:
        marker, (frame, side, measurement) = item
        marker_path = output_path if marker == "A" else output_path.with_name(f"evidence-{marker.lower()}.jpg")
        marker_url = media_url if marker == "A" else f"{media_root}/evidence-{marker.lower()}.jpg"
        _render_evidence(video_path, frame, sport, marker, side, measurement, marker_path, swim_stroke)
        return marker, marker_url

    with ThreadPoolExecutor(max_workers=min(4, len(evidences)), thread_name_prefix="evidence") as executor:
        return dict(executor.map(render, evidences.items()))


def _render_evidence_clips(video_path: Path, insights: list[dict], output_path: Path, media_url: str) -> None:
    media_root = media_url.rsplit("/", 1)[0]

    def render(insight: dict) -> tuple[str, str]:
        marker = str(insight["marker"]).lower()
        center = _timestamp_seconds(str(insight["timestamp"]))
        clip_path = output_path.with_name(f"clip-{marker}.mp4")
        capture, fps, _, width, height, duration = _video_metadata(video_path)
        start = max(0.0, center - 1.0)
        end = min(duration, center + 1.2)
        capture.set(cv2.CAP_PROP_POS_FRAMES, int(start * fps))
        writer = cv2.VideoWriter(str(clip_path), cv2.VideoWriter_fourcc(*"mp4v"), min(fps, 30.0), (width, height))
        current = start
        while writer.isOpened() and current <= end:
            ok, frame = capture.read()
            if not ok:
                break
            writer.write(frame)
            current += 1.0 / fps
        writer.release()
        capture.release()
        return str(insight["marker"]), f"{media_root}/clip-{marker}.mp4"

    with ThreadPoolExecutor(max_workers=min(2, len(insights)), thread_name_prefix="clip") as executor:
        clips = dict(executor.map(render, insights))
    for insight in insights:
        insight["clip"] = clips.get(str(insight["marker"]))
        insight["clipStartSeconds"] = max(0.0, _timestamp_seconds(str(insight["timestamp"])) - 1.0)


def _motion_cycles(pose_frames: list[PoseFrame]) -> list[dict]:
    samples: list[tuple[float, float]] = []
    for item in pose_frames:
        if _landmark_visibility(item, [POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER, POSE.LEFT_WRIST, POSE.RIGHT_WRIST]) < 0.48:
            continue
        shoulder = _midpoint(item.landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        hip = _midpoint(item.landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP)
        torso = max(0.04, _distance(shoulder, hip))
        reach = max(_distance(_point(item.landmarks, POSE.LEFT_WRIST), shoulder), _distance(_point(item.landmarks, POSE.RIGHT_WRIST), shoulder)) / torso
        samples.append((item.timestamp, reach))
    peaks: list[float] = []
    for index in range(1, len(samples) - 1):
        if samples[index][1] >= samples[index - 1][1] and samples[index][1] >= samples[index + 1][1]:
            if not peaks or samples[index][0] - peaks[-1] >= 0.7:
                peaks.append(samples[index][0])
    return [
        {"id": f"cycle-{index + 1:02d}", "start": round(start, 2), "end": round(end, 2), "duration": round(end - start, 2), "confidence": 0.78}
        for index, (start, end) in enumerate(zip(peaks, peaks[1:]))
        if 0.7 <= end - start <= 5.0
    ][:20]


def _enrich_report(report: dict, pose_frames: list[PoseFrame], metadata: dict[str, float]) -> dict:
    cycles = _motion_cycles(pose_frames)
    blockers: list[str] = []
    if metadata["detectionRatio"] < 0.45:
        blockers.append("身体关键部位被水花或画面边缘遮挡较多")
    if report["sport"] == "swimming" and len(cycles) < 2:
        blockers.append("没有看清至少两个完整动作周期")
    if report.get("swimStroke", {}).get("stroke") == "unknown":
        blockers.append("泳姿识别证据不足，需要确认或重新拍摄")
    report["qualityAssessment"] = {
        "status": "pass" if not blockers else "limited",
        "quality": "good" if metadata["confidence"] >= 75 and not blockers else "usable" if not blockers else "limited",
        "checks": {
            "singlePerson": True,
            "fullBodyCoverage": round(metadata["detectionRatio"], 2),
            "cameraStability": "usable",
            "visibleCycles": len(cycles),
            "view": "side_or_oblique",
        },
        "blockingIssues": blockers,
        "suggestions": ["固定机位并让头、手、髋和脚连续留在画面中"] if blockers else [],
    }
    report["cycles"] = cycles
    primary = next((item for item in report["insights"] if item["severity"] in {"focus", "observe"}), report["insights"][0])
    needs_recapture = report.get("swimStroke", {}).get("stroke") == "unknown"
    report["prescription"] = {
        "priorityIssueId": primary["id"],
        "reason": primary.get("impact", "这是当前最影响动作稳定性的问题。"),
        "drill": primary["action"],
        "volume": "重新拍摄 1 段至少两个完整周期的视频" if needs_recapture else "4 组，每组 25 米",
        "rest": "固定侧面机位，全身保持入镜" if needs_recapture else "组间休息 20 秒",
        "focusCue": primary["title"],
        "successCue": primary.get("successCue", "动作保持连续，不需要额外用力补偿。"),
    }
    report["pipeline"] = {
        "pipelineVersion": "2.0.0",
        "poseModelVersion": "mediapipe-0.10.21",
        "ruleVersion": "swim-rules-2",
        "promptVersion": "coach-review-1",
    }
    report["modelReview"] = {
        "status": "engineering_fallback",
        "reason": "未配置多模态模型，当前由姿态模型、时间序列规则和证据门槛生成。",
        "evidenceValidated": not blockers,
    }
    return report


def _running_report(
    video_path: Path,
    report_id: str,
    file_name: str,
    pose_frames: list[PoseFrame],
    metadata: dict[str, float],
    media_url: str,
    output_path: Path,
) -> dict:
    values, evidences = _running_measurements(pose_frames)
    lean = values["torsoLean"]
    knee_difference = values["kneeDifference"]
    ankle_offset = values["ankleOffsetRatio"]
    arm_difference = values["armDifference"]
    detection = metadata["detectionRatio"] * 100

    lean_score = _clamp(100 - abs(lean - 8) * 4)
    symmetry_score = _clamp(100 - knee_difference * 1.8)
    offset_score = _clamp(100 - max(0.0, ankle_offset - 0.18) * 130)
    stability_score = _clamp(100 - values["torsoLeanStd"] * 6)
    score = round(0.3 * lean_score + 0.28 * symmetry_score + 0.27 * offset_score + 0.15 * stability_score)

    if ankle_offset > 0.3:
        headline = "脚落得离身体有点远"
        primary_summary = "这个动作时刻，脚先伸到身体前方才落地，后腿还没有完全跟上重心。"
        primary_impact = "脚在身体前方落地会产生刹车感，腿需要多用一次力才能继续向前。"
        primary_action = "下次慢跑时做 3 组 30 秒小步快跑，只想一件事：脚往身体正下方放。"
        primary_cue = "脚步声会更轻，落地时脚掌就在髋部下方，不会有向前够地的感觉。"
        primary_severity = "focus"
    else:
        headline = "脚基本落在身体下方"
        primary_summary = "这个动作时刻，脚基本落在身体下方，落地位置和重心配合得比较自然。"
        primary_impact = "落点靠近身体，触地时更容易顺势向前，不会明显刹车。"
        primary_action = "继续保持自然步幅，不要为了跑快主动向前够脚。"
        primary_cue = "落地声音轻，身体能顺畅越过支撑脚。"
        primary_severity = "good"

    if lean > 16:
        lean_title = "上半身压得太低"
        lean_impact = "从腰部折下去会限制抬腿和呼吸，跑久后腰背更容易紧。"
        lean_action = "下一组跑 30 秒时把身体想成一块直板，只从脚踝整体轻轻向前。"
        lean_cue = "腹部不会被挤压，肩膀、髋部和脚踝仍像在一条直线上。"
        lean_severity = "observe"
    elif lean < 3:
        lean_title = "身体几乎完全直立"
        lean_impact = "加速时身体重心不容易自然向前，需要更多蹬地力量。"
        lean_action = "加速 20 秒时保持身体挺直，从脚踝整体轻轻向前倾。"
        lean_cue = "会感觉重心自己向前移动，而不是弯腰去追速度。"
        lean_severity = "observe"
    else:
        lean_title = "上半身角度保持得不错"
        lean_impact = "身体能顺着跑动方向前进，不会把力量浪费在上下起伏上。"
        lean_action = "继续放松肩颈和腰部，保持现在的身体角度。"
        lean_cue = "呼吸顺畅，腰部没有折叠或后仰的紧张感。"
        lean_severity = "good"

    evidence_urls = _render_evidence_set(video_path, "running", evidences, output_path, media_url)
    duration = metadata["durationSeconds"]
    return {
        "id": report_id,
        "source": "video",
        "sport": "running",
        "title": "跑步 · 视频动作分析",
        "date": "刚刚",
        "duration": f"{int(duration // 60):02d}:{int(round(duration % 60)):02d} 视频",
        "score": score,
        "confidence": round(metadata["confidence"]),
        "quality": "清晰" if metadata["confidence"] >= 75 else "可用" if metadata["confidence"] >= 50 else "较低",
        "headline": headline,
        "summary": f"我们在多个跑步动作时刻都观察到了这一点。{primary_summary}",
        "image": media_url,
        "metadata": metadata,
        "keyMeasurements": {
            "torsoLean": {"value": round(float(lean), 2), "unit": "°", "label": "躯干前倾", "betterWhen": "range", "target": 10.0},
            "ankleOffsetRatio": {"value": round(float(ankle_offset), 4), "unit": "%身高", "label": "脚踝前伸", "betterWhen": "lower"},
            "kneeDifference": {"value": round(float(knee_difference), 2), "unit": "°", "label": "左右膝角差", "betterWhen": "lower"},
            "armDifference": {"value": round(float(arm_difference), 2), "unit": "°", "label": "摆臂差异", "betterWhen": "lower"},
        },
        "metrics": [
            {"label": "躯干前倾", "value": f"{lean:.1f}", "unit": "°", "delta": "由肩髋轴计算", "tone": "neutral"},
            {"label": "脚踝前伸", "value": f"{ankle_offset * 100:.0f}", "unit": "%身高", "delta": "无实物标尺", "tone": "warning" if ankle_offset > 0.3 else "positive"},
            {"label": "左右膝角差", "value": f"{knee_difference:.1f}", "unit": "°", "delta": "越小越接近", "tone": "positive" if knee_difference < 10 else "warning"},
            {"label": "姿态覆盖", "value": f"{detection:.0f}", "unit": "%", "delta": "有效采样帧", "tone": "positive" if detection >= 60 else "neutral"},
        ],
        "insights": [
            {"id": "landing", "title": headline, "summary": primary_summary, "impact": primary_impact, "action": primary_action, "successCue": primary_cue, "severity": primary_severity, "timestamp": _format_timestamp(evidences["A"][0].timestamp), "marker": "A", "image": evidence_urls["A"]},
            {"id": "posture", "title": lean_title, "summary": "这个动作时刻，上半身没有和髋部一起向前，而是从腰部单独折了下去。" if lean > 16 else "这个动作时刻，上半身和髋部能一起移动，没有明显弯腰或后仰。", "impact": lean_impact, "action": lean_action, "successCue": lean_cue, "severity": lean_severity, "timestamp": _format_timestamp(evidences["B"][0].timestamp), "marker": "B", "image": evidence_urls["B"]},
            {"id": "symmetry", "title": "两条腿弯曲幅度比较接近" if knee_difference < 10 else "两条腿弯曲幅度不太一样", "summary": "这个动作时刻，一侧膝盖明显弯得更多，两只脚的落地准备不一致。" if knee_difference >= 10 else "这个动作时刻，两条腿的弯曲和落地准备比较一致。", "impact": "两侧动作差异过大会让身体左右晃动，也可能让一条腿更早疲劳。" if knee_difference >= 10 else "两侧动作接近，有助于保持稳定节奏。", "action": "用相同速度跑 3 组 20 秒，注意两只脚的落地声是否一样。", "successCue": "左右脚落地声和支撑时间接近，身体不会向一侧偏。", "severity": "good" if knee_difference < 10 else "observe", "timestamp": _format_timestamp(evidences["C"][0].timestamp), "marker": "C", "image": evidence_urls["C"]},
            {"id": "arms", "title": "两侧摆臂节奏接近" if arm_difference < 15 else "两只手臂摆动不同步", "summary": "这个动作时刻，一只手臂已经向后，另一只还停在身体前方，摆臂节奏没有对上。" if arm_difference >= 15 else "这个动作时刻，两只手臂能够一前一后自然配合。", "impact": "摆臂不同步会带动肩膀左右扭，让步伐也跟着不稳定。" if arm_difference >= 15 else "摆臂配合自然，有助于保持躯干和步伐稳定。", "action": "下一次慢跑 3 组 20 秒，双手放松握拳，只想手肘向身后送。", "successCue": "双手都沿身体两侧前后移动，肩膀不会跟着左右晃。", "severity": "good" if arm_difference < 15 else "observe", "timestamp": _format_timestamp(evidences["D"][0].timestamp), "marker": "D", "image": evidence_urls["D"]},
        ],
        "fileName": file_name,
    }


def _swimming_report(
    video_path: Path,
    report_id: str,
    file_name: str,
    pose_frames: list[PoseFrame],
    metadata: dict[str, float],
    media_url: str,
    output_path: Path,
    stroke_result: dict[str, object],
) -> dict:
    values, evidences = _swimming_measurements(pose_frames)
    head_deviation = values["headDeviation"]
    body_issue = values["bodyIssue"]
    front_arm_drop = values["frontArmDrop"]
    knee_flexion = values["kneeFlexion"]
    detection = metadata["detectionRatio"] * 100

    head_reliable = values["headSamples"] >= 8
    body_reliable = values["bodySamples"] >= 8
    reach_reliable = values["reachEvents"] >= 2
    kick_reliable = values["kickSamples"] >= 8
    head_problem = head_reliable and values["headEpisodes"] >= 2 and head_deviation >= 0.36
    body_problem = body_reliable and values["bodyEpisodes"] >= 2 and body_issue >= 14
    reach_problem = reach_reliable and front_arm_drop >= 0.28
    kick_problem = kick_reliable and values["kickEpisodes"] >= 2 and knee_flexion >= 38

    dimension_scores = [
        68 if head_problem else 88 if head_reliable else 76,
        68 if body_problem else 88 if body_reliable else 76,
        68 if reach_problem else 88 if reach_reliable else 76,
        68 if kick_problem else 88 if kick_reliable else 76,
    ]
    score = round(float(np.mean(dimension_scores)))

    if not head_reliable:
        headline = "头部动作暂时看不清"
        primary_summary = "水花或拍摄角度遮住了头和肩膀，这次不能可靠判断呼吸时有没有抬头。"
        primary_impact = "看不清时直接下结论容易把水花误当成动作问题。"
        primary_action = "下次从泳道侧面拍摄，让头、肩和髋部连续完整入镜。"
        primary_cue = "回放时能连续看到头部随肩膀一起转动，而不是被水花遮住。"
        severity = "observe"
    elif head_problem:
        headline = "呼吸时头部偏离身体线"
        primary_summary = "多个呼吸动作里，头先向上抬再转向侧面，肩膀和髋部随后下沉。"
        primary_impact = "抬头会把身体前端顶高、髋腿压低，让每次换气都多出一段阻力。"
        primary_action = "做 4 趟侧身打腿换气：眼睛先看池底，随肩膀侧转，只让一侧泳镜离开水面。"
        primary_cue = "吸气时嘴能露出水面，但头顶仍朝向泳池前方，臀部不会明显下沉。"
        severity = "focus"
    else:
        headline = "换气时头部能顺着身体转动"
        primary_summary = "头部大多和肩膀一起侧转，没有反复向前抬头。"
        primary_impact = "稳定的头位能帮助髋腿贴近水面，减少换气带来的减速。"
        primary_action = "继续保持眼睛看向池底，换气时只转头、不抬下巴。"
        primary_cue = "换气前后速度连续，头回到水中时身体不会突然下沉。"
        severity = "good"

    def insight(
        marker: str,
        insight_id: str,
        reliable: bool,
        problem: bool,
        good_title: str,
        problem_title: str,
        good_summary: str,
        problem_summary: str,
        impact: str,
        action: str,
        cue: str,
        unclear_subject: str,
    ) -> dict:
        if not reliable:
            title = f"{unclear_subject}暂时看不清"
            summary = f"这段视频里{unclear_subject}被水花或画面边缘遮挡，证据不足，暂不判断好坏。"
            insight_impact = "补齐拍摄证据后再判断，能避免给出错误训练方向。"
            insight_action = "下次从泳道侧面固定拍摄，让头、手臂、髋部和脚连续完整入镜。"
            insight_cue = "回放时能连续看到至少两个完整划水周期。"
            insight_severity = "observe"
        else:
            title = problem_title if problem else good_title
            summary = problem_summary if problem else good_summary
            insight_impact = impact
            insight_action = action
            insight_cue = cue
            insight_severity = "observe" if problem else "good"
        return {"id": insight_id, "title": title, "summary": summary, "impact": insight_impact, "action": insight_action, "successCue": insight_cue, "severity": insight_severity, "timestamp": _format_timestamp(evidences[marker][0].timestamp), "marker": marker, "image": evidence_urls[marker]}

    swim_stroke = str(stroke_result["stroke"])
    stroke_name = str(stroke_result["strokeName"])
    evidence_urls = _render_evidence_set(video_path, "swimming", evidences, output_path, media_url, swim_stroke)
    duration = metadata["durationSeconds"]
    return {
        "id": report_id,
        "source": "video",
        "sport": "swimming",
        "title": f"{stroke_name} · 视频动作分析",
        "date": "刚刚",
        "duration": f"{int(duration // 60):02d}:{int(round(duration % 60)):02d} 视频",
        "score": score,
        "confidence": round(metadata["confidence"]),
        "quality": "清晰" if metadata["confidence"] >= 75 else "可用" if metadata["confidence"] >= 50 else "较低",
        "headline": headline,
        "summary": primary_summary,
        "image": media_url,
        "metadata": metadata,
        "swimStroke": stroke_result,
        "keyMeasurements": {
            "headDeviation": {"value": round(float(head_deviation), 4), "unit": "", "label": "头位偏离", "betterWhen": "lower"},
            "bodyIssue": {"value": round(float(body_issue), 4), "unit": "", "label": "身体线下沉", "betterWhen": "lower"},
            "frontArmDrop": {"value": round(float(front_arm_drop), 4), "unit": "", "label": "前手下压", "betterWhen": "lower"},
            "kneeFlexion": {"value": round(float(knee_flexion), 2), "unit": "°", "label": "打腿膝屈曲", "betterWhen": "lower"},
        },
        "metrics": [
            {"label": "头位", "value": "需改进" if head_problem else "稳定" if head_reliable else "待补拍", "unit": "", "delta": "跨多个呼吸动作", "tone": "warning" if head_problem else "positive" if head_reliable else "neutral"},
            {"label": "身体线", "value": "需改进" if body_problem else "稳定" if body_reliable else "待补拍", "unit": "", "delta": "肩髋脚整体趋势", "tone": "warning" if body_problem else "positive" if body_reliable else "neutral"},
            {"label": "前伸", "value": "过早下压" if reach_problem else "顺畅" if reach_reliable else "待补拍", "unit": "", "delta": "只比较前伸事件", "tone": "warning" if reach_problem else "positive" if reach_reliable else "neutral"},
            {"label": "姿态覆盖", "value": f"{detection:.0f}", "unit": "%", "delta": "水面遮挡会影响", "tone": "positive" if detection >= 60 else "neutral"},
        ],
        "insights": [
            {"id": "head", "title": headline, "summary": primary_summary, "impact": primary_impact, "action": primary_action, "successCue": primary_cue, "severity": severity, "timestamp": _format_timestamp(evidences["A"][0].timestamp), "marker": "A", "image": evidence_urls["A"]},
            insight("B", "line", body_reliable, body_problem, "身体线保持得比较舒展", "身体向下形成了明显斜坡", "多个动作里，肩、髋和脚能朝同一方向延伸，身体没有反复折下去。", "多个动作里，髋腿会落到肩膀下方，身体像一条向下的斜坡。", "髋腿下沉会增大迎水面积，同样的划水力量滑行距离会变短。", "做 4 趟轻松游：眼睛看池底、腹部轻轻收紧，想象有人从脚后跟把身体拉长。", "会感觉臀部更接近水面，脚后跟偶尔轻触水面。", "身体线"),
            insight("C", "reach", reach_reliable, reach_problem, "前手能先向前伸长再抓水", "前手还没伸长就开始向下压", "在前手到达最远位置时，手臂仍朝前延伸，没有急着向下压水。", "前手刚到头前方就开始下压，身体来不及借助前伸继续滑行。", "过早下压会缩短每次划水的有效距离，也容易让头肩跟着抬起。", "做 4 趟追赶游：前手保持向前，另一只手快碰到前手时，再开始抓水。", "每次入水后都能感到身体先向前滑一下，再由前臂把水向后送。", "前伸动作"),
            insight("D", "kick", kick_reliable, kick_problem, "打腿幅度轻而连续", "打腿主要从膝盖发力", "多个打腿动作里，膝盖保持自然放松，整条腿由髋部带动。", "多个动作里，小腿先向后折再甩水，看起来像在水中踩踏。", "从膝盖用力会让大腿迎水，增加阻力，也更快消耗体力。", "做 4 组 20 秒侧身打腿：脚踝放松，从髋部发起小幅、连续的上下摆动。", "水花集中在脚边，膝盖不会频繁露出水面，腿部感觉轻而不断。", "打腿动作"),
        ],
        "fileName": file_name,
    }


def _adapt_swimming_report_to_stroke(report: dict, stroke_result: dict[str, object]) -> dict:
    stroke = str(stroke_result["stroke"])
    if stroke == "freestyle":
        return report

    profiles = {
        "backstroke": {
            "headline": "先让头、髋和打腿保持在同一条线上",
            "summary": "系统识别为仰泳。建议先稳定仰卧身体线，再检查手臂入水和连续打腿。",
            "insights": [
                ("头部保持稳定朝上", "后脑勺自然放在水里，不要用下巴寻找脚的方向。", "下巴微收、眼睛看上方，让水面停在耳朵附近。", "头不左右摇，髋部更容易贴近水面。"),
                ("髋部跟着胸口一起浮起", "身体中段下沉会让腿部承担更多抬升工作。", "轻轻抬胸并收紧腹部，想象肚脐靠近水面。", "髋部不再往下掉，打腿水花集中在脚边。"),
                ("手臂沿肩线方向入水", "手臂跨过头部中线会带动身体蛇形摆动。", "小拇指先入水，手掌落在同侧肩膀延长线上。", "每次入水身体仍朝泳道正前方移动。"),
                ("打腿要小而连续", "膝盖大幅露出水面会形成踩水动作并增加阻力。", "从髋部发起快速小幅打腿，脚踝保持放松。", "脚尖在水面附近持续翻水，膝盖不明显露出。"),
            ],
        },
        "breaststroke": {
            "headline": "先把前伸、收腿和滑行接成清楚的顺序",
            "summary": "系统识别为蛙泳。建议重点检查手腿配合和蹬夹后的身体伸展。",
            "insights": [
                ("换气后及时把头放回身体线", "头一直抬在水面会让髋腿持续下沉。", "吸气后低头前伸，让耳朵重新回到手臂之间。", "双手前伸时能看到池底，身体自然向前滑。"),
                ("蹬夹后先保持身体伸长", "没有滑行会让动作变得急促，每次蹬腿的推进没有被充分利用。", "每次蹬夹结束后保持一次流线，再开始下一次划手。", "会感到身体安静向前滑一小段，而不是立即忙着划手。"),
                ("双手向前伸直后再滑行", "手臂过早向外划会缩短前伸并打乱节奏。", "双手在胸前合拢后快速向前送，手臂夹住耳朵。", "双手、头和胸口朝同一方向延伸。"),
                ("收腿窄一些，脚掌向后蹬夹", "膝盖打开过宽会增加迎水面积，也容易把力量蹬向两侧。", "脚跟靠近臀部，膝盖不超过肩宽，再把脚掌向后蹬开并合拢。", "蹬腿后双腿能快速并拢，推进方向主要向前。"),
            ],
        },
        "butterfly": {
            "headline": "先让躯干波动带动双臂和双腿",
            "summary": "系统识别为蝶泳。建议先检查身体波动、双臂同步和两次海豚腿节奏。",
            "insights": [
                ("换气时头部向前贴水", "过度抬头会压低髋部，让手臂回臂更费力。", "下巴贴近水面向前吸气，双手入水前让头先回到水中。", "头先入水、手随后入水，髋部不会突然下沉。"),
                ("波动从胸口传到髋部", "只靠腰部折叠会让身体上下起伏过大。", "先轻压胸口，再让髋部和双腿顺势跟随，不要主动塌腰。", "波浪连续经过身体，动作不会卡在腰部。"),
                ("双臂同时入水后向前延伸", "两臂不同步会让身体向一侧扭转并打乱第二次打腿。", "双臂放松回臂，在肩膀前方同时入水并向前伸长。", "两只手几乎同时碰水，身体继续直线前进。"),
                ("两次海豚腿要服务于划臂节奏", "膝盖主动大幅甩腿会增加阻力，也难以维持连续波动。", "手入水时轻踢一次，推水结束时再有力踢一次，动作从髋部发起。", "两次打腿都能和手臂动作对上，不会单独抢拍。"),
            ],
        },
        "unknown": {
            "headline": "泳姿证据不足，暂不套用专项规则",
            "summary": "画面中的手臂或腿部被遮挡，系统无法可靠区分自由泳、蛙泳、仰泳或蝶泳。",
            "insights": [
                ("需要看到头部与肩膀", "当前画面不足以判断呼吸和身体朝向。", "从泳道侧面固定机位拍摄，保留头部和肩膀。", "回放能连续看见头部动作。"),
                ("需要看到完整身体线", "身体被画面边缘裁切后无法判断髋腿位置。", "让头到脚都留在画面内，并减少镜头跟随晃动。", "至少两个完整周期全身不出画。"),
                ("需要看到双臂动作关系", "判断泳姿依赖双臂是交替还是同步。", "拍摄时不要让近侧手臂长期遮住另一只手臂。", "回放能分辨两只手的入水和划水时机。"),
                ("需要看到收腿或打腿方式", "腿部动作是区分泳姿的重要证据。", "机位稍微拉远，让膝盖、脚踝和脚掌完整出现。", "回放能看清至少两次完整腿部动作。"),
            ],
        },
    }
    profile = profiles.get(stroke, profiles["unknown"])
    report["headline"] = profile["headline"]
    report["summary"] = profile["summary"]
    for insight, content in zip(report["insights"], profile["insights"]):
        insight["title"], insight["summary"], insight["action"], insight["successCue"] = content
        insight["impact"] = content[1]
        insight["severity"] = "observe"
    return report


def analyze_video(
    video_path: Path,
    sport: str,
    report_id: str,
    file_name: str,
    output_path: Path,
    media_url: str,
    progress: ProgressCallback,
    swim_stroke_hint: str | None = None,
) -> dict:
    pose_frames, metadata = _extract_pose_frames(video_path, progress)
    body_axis_angle = _body_axis_angle_from_horizontal(pose_frames)
    metadata["bodyAxisAngleFromHorizontal"] = body_axis_angle
    if sport == "running" and body_axis_angle < 30:
        raise AnalysisError("SPORT_MISMATCH", "画面中的身体长期接近水平，更像游泳视频。请切换到游泳后重新分析。")
    if sport == "swimming" and body_axis_angle > 55:
        raise AnalysisError("SPORT_MISMATCH", "画面中的身体长期接近直立，更像跑步视频。请切换到跑步后重新分析。")
    stroke_result: dict[str, object] | None = None
    if sport == "swimming":
        progress(78, "识别泳姿与动作周期")
        stroke_result = _classify_swim_stroke(pose_frames)
        if swim_stroke_hint in SWIM_STROKE_NAMES and swim_stroke_hint != "unknown":
            stroke_result["stroke"] = swim_stroke_hint
            stroke_result["strokeName"] = SWIM_STROKE_NAMES[swim_stroke_hint]
            stroke_result["reusedFromSameVideo"] = True
        metadata["swimStrokeConfidence"] = float(stroke_result["confidence"])
    progress(82, "计算专项动作指标")
    if sport == "running":
        report = _running_report(video_path, report_id, file_name, pose_frames, metadata, media_url, output_path)
    elif sport == "swimming":
        assert stroke_result is not None
        report = _swimming_report(video_path, report_id, file_name, pose_frames, metadata, media_url, output_path, stroke_result)
        report = _adapt_swimming_report_to_stroke(report, stroke_result)
    else:
        raise AnalysisError("SPORT_NOT_SUPPORTED", "当前只支持跑步和游泳。")
    report = _enrich_report(report, pose_frames, metadata)
    progress(92, "生成证据短片与训练处方")
    _render_evidence_clips(video_path, report["insights"], output_path, media_url)
    progress(96, "完成证据与质量校验")
    return report
