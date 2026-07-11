from __future__ import annotations

import math
import time
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


def _extract_pose_frames(
    path: Path,
    progress: ProgressCallback,
) -> tuple[list[PoseFrame], dict[str, float]]:
    capture, fps, frame_count, width, height, duration = _video_metadata(path)
    target_sample_fps = min(12.0, fps)
    sample_count = min(1200, max(40, int(math.ceil(duration * target_sample_fps))))
    indices = np.unique(np.linspace(0, frame_count - 1, sample_count, dtype=np.int32))
    pose_frames: list[PoseFrame] = []

    started_at = time.perf_counter()
    progress(12, "顺序读取视频帧")
    with mp.solutions.pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        enable_segmentation=False,
        min_detection_confidence=0.4,
        min_tracking_confidence=0.4,
    ) as pose:
        position = 0
        for frame_index in range(frame_count):
            if position >= len(indices):
                break
            ok = capture.grab()
            if not ok:
                break
            if frame_index != int(indices[position]):
                continue
            ok, frame = capture.retrieve()
            if not ok:
                position += 1
                continue
            inference_frame = frame
            longest_side = max(frame.shape[:2])
            if longest_side > 640:
                inference_scale = 640 / longest_side
                inference_frame = cv2.resize(
                    frame,
                    (int(frame.shape[1] * inference_scale), int(frame.shape[0] * inference_scale)),
                    interpolation=cv2.INTER_AREA,
                )
            result = pose.process(cv2.cvtColor(inference_frame, cv2.COLOR_BGR2RGB))
            if result.pose_landmarks:
                landmarks = np.array(
                    [[item.x, item.y, item.z, item.visibility] for item in result.pose_landmarks.landmark],
                    dtype=np.float32,
                )
                quality = float(np.mean(landmarks[CORE_LANDMARKS, 3]))
                if quality >= 0.32:
                    pose_frames.append(
                        PoseFrame(
                            frame_index=int(frame_index),
                            timestamp=float(frame_index / fps),
                            landmarks=landmarks,
                            quality=quality,
                        )
                    )
            position += 1
            progress(18 + int(55 * position / len(indices)), "跟踪身体关键点")

    capture.release()
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
        "detectedFrames": len(pose_frames),
        "detectionRatio": detection_ratio,
        "confidence": confidence,
        "analysisSeconds": time.perf_counter() - started_at,
        "inferenceMaxSide": 640,
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


def _swimming_measurements(pose_frames: list[PoseFrame]) -> tuple[dict[str, float], dict[str, tuple[PoseFrame, int, float]]]:
    line_deviations: list[float] = []
    reach_ratios: list[float] = []
    elbow_differences: list[float] = []
    knee_flexions: list[float] = []
    reach_candidates: list[tuple[float, PoseFrame, int, float]] = []
    line_candidates: list[tuple[float, PoseFrame, int, float]] = []
    arm_candidates: list[tuple[float, PoseFrame, int, float]] = []
    kick_candidates: list[tuple[float, PoseFrame, int, float]] = []

    for item in pose_frames:
        landmarks = item.landmarks
        mid_shoulder = _midpoint(landmarks, POSE.LEFT_SHOULDER, POSE.RIGHT_SHOULDER)
        mid_hip = _midpoint(landmarks, POSE.LEFT_HIP, POSE.RIGHT_HIP)
        mid_ankle = _midpoint(landmarks, POSE.LEFT_ANKLE, POSE.RIGHT_ANKLE)
        body_angle = _angle(mid_shoulder, mid_hip, mid_ankle)
        line_deviation = abs(180.0 - body_angle)
        line_deviations.append(line_deviation)

        shoulder_width = max(
            0.03,
            _distance(_point(landmarks, POSE.LEFT_SHOULDER), _point(landmarks, POSE.RIGHT_SHOULDER)),
        )
        reach_ratio = _distance(
            _point(landmarks, POSE.LEFT_WRIST),
            _point(landmarks, POSE.RIGHT_WRIST),
        ) / shoulder_width
        reach_ratios.append(reach_ratio)

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
        elbow_difference = abs(left_elbow - right_elbow)
        elbow_differences.append(elbow_difference)

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
        knee_flexion = max(180.0 - left_knee, 180.0 - right_knee)
        knee_flexions.append(knee_flexion)
        reach_candidates.append((abs(reach_ratio - 1.0), item, 0, reach_ratio))
        line_candidates.append((line_deviation, item, 0, line_deviation))
        arm_candidates.append((elbow_difference, item, 0, elbow_difference))
        kick_candidates.append((knee_flexion, item, 0, knee_flexion))

    line_deviation = float(np.median(line_deviations))
    reach_ratio = float(np.median(reach_ratios))
    elbow_difference = float(np.median(elbow_differences))
    knee_flexion = float(np.percentile(knee_flexions, 75))
    selected: list[PoseFrame] = []
    evidences = {
        "A": _pick_distinct_frame(sorted(reach_candidates, reverse=True, key=lambda value: value[0]), selected),
        "B": _pick_distinct_frame(sorted(line_candidates, reverse=True, key=lambda value: value[0]), selected),
        "C": _pick_distinct_frame(sorted(arm_candidates, reverse=True, key=lambda value: value[0]), selected),
        "D": _pick_distinct_frame(sorted(kick_candidates, reverse=True, key=lambda value: value[0]), selected),
    }
    values = {
        "lineDeviation": line_deviation,
        "reachRatio": reach_ratio,
        "elbowDifference": elbow_difference,
        "kneeFlexion": knee_flexion,
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
        concerning = not 0.72 <= measurement <= 1.55 if marker == "A" else measurement >= 8 if marker == "B" else measurement >= 12 if marker == "C" else measurement >= 35
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
        left_wrist = _pixel(_point(landmarks, POSE.LEFT_WRIST), width, height)
        right_wrist = _pixel(_point(landmarks, POSE.RIGHT_WRIST), width, height)
        cv2.line(image, left_wrist, right_wrist, actual_blue, max(2, width // 420), cv2.LINE_AA)
        cv2.circle(image, left_wrist, radius, actual_blue, -1, cv2.LINE_AA)
        cv2.circle(image, right_wrist, radius, actual_blue, -1, cv2.LINE_AA)
        midpoint = ((left_wrist[0] + right_wrist[0]) // 2, (left_wrist[1] + right_wrist[1]) // 2)
        reach_issue = "手入水太靠近中间" if measurement < 0.72 else "手入水打开得太宽" if measurement > 1.55 else "手入水位置合适"
        label = reach_issue
        label_origin = (midpoint[0] - 100, midpoint[1] + 20)
        focus_points = [
            left_wrist,
            right_wrist,
            _pixel(_point(landmarks, POSE.LEFT_ELBOW), width, height),
            _pixel(_point(landmarks, POSE.RIGHT_ELBOW), width, height),
        ]
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
        for shoulder_landmark, elbow_landmark, wrist_landmark in [
            (POSE.LEFT_SHOULDER, POSE.LEFT_ELBOW, POSE.LEFT_WRIST),
            (POSE.RIGHT_SHOULDER, POSE.RIGHT_ELBOW, POSE.RIGHT_WRIST),
        ]:
            points = [_pixel(_point(landmarks, landmark), width, height) for landmark in (shoulder_landmark, elbow_landmark, wrist_landmark)]
            cv2.polylines(image, [np.array(points, dtype=np.int32)], False, actual_blue, max(2, width // 420), cv2.LINE_AA)
            for point in points:
                cv2.circle(image, point, radius, actual_blue, -1, cv2.LINE_AA)
            focus_points.extend(points)
        label = "两只手臂动作差异大" if measurement >= 12 else "两侧划水动作接近"
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
        label = "打腿时膝盖弯得太多" if measurement >= 35 else "打腿幅度比较轻松"

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
) -> dict[str, str]:
    urls: dict[str, str] = {}
    media_root = media_url.rsplit("/", 1)[0]
    for marker, (frame, side, measurement) in evidences.items():
        marker_path = output_path if marker == "A" else output_path.with_name(f"evidence-{marker.lower()}.jpg")
        marker_url = media_url if marker == "A" else f"{media_root}/evidence-{marker.lower()}.jpg"
        _render_evidence(video_path, frame, sport, marker, side, measurement, marker_path)
        urls[marker] = marker_url
    return urls


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
) -> dict:
    values, evidences = _swimming_measurements(pose_frames)
    line_deviation = values["lineDeviation"]
    reach_ratio = values["reachRatio"]
    elbow_difference = values["elbowDifference"]
    knee_flexion = values["kneeFlexion"]
    detection = metadata["detectionRatio"] * 100

    line_score = _clamp(100 - line_deviation * 4)
    reach_score = _clamp(100 - abs(reach_ratio - 1.0) * 55)
    symmetry_score = _clamp(100 - elbow_difference * 1.5)
    score = round(0.4 * line_score + 0.32 * reach_score + 0.28 * symmetry_score)

    if reach_ratio < 0.72:
        headline = "手入水时太靠近头部中间"
        primary_impact = "手臂向中间交叉会带动身体左右扭，后续抱水也更难找到稳定支点。"
        primary_action = "下次做 4 趟轻松游，想象肩膀前方各有一条轨道，手掌沿自己的轨道入水。"
        primary_cue = "入水后头部保持不动，身体不会被一只手带着左右摇摆。"
        severity = "focus"
    elif reach_ratio > 1.55:
        headline = "手入水时打开得太宽"
        primary_impact = "手臂离身体太远会缩短有效划水距离，也更难把水向后推。"
        primary_action = "下次做 4 趟轻松游，让手掌从肩膀正前方入水，再贴着耳朵向前伸。"
        primary_cue = "前伸时肩膀贴近耳朵，手掌不会向泳道两侧滑开。"
        severity = "observe"
    else:
        headline = "手掌基本从肩膀正前方入水"
        primary_impact = "这个入水位置能让身体保持稳定，也为后续抱水留出完整空间。"
        primary_action = "继续保持当前入水方向，手臂完全伸长后再开始抱水。"
        primary_cue = "每次入水后身体都继续向前滑，不会突然左右摆动。"
        severity = "good"

    primary_summary = "这个动作时刻，手掌没有沿肩膀正前方入水，身体会被手臂带偏。" if severity != "good" else "这个动作时刻，手掌能从肩膀正前方入水，前伸方向比较稳定。"
    evidence_urls = _render_evidence_set(video_path, "swimming", evidences, output_path, media_url)
    duration = metadata["durationSeconds"]
    return {
        "id": report_id,
        "source": "video",
        "sport": "swimming",
        "title": "游泳 · 视频动作分析",
        "date": "刚刚",
        "duration": f"{int(duration // 60):02d}:{int(round(duration % 60)):02d} 视频",
        "score": score,
        "confidence": round(metadata["confidence"]),
        "quality": "清晰" if metadata["confidence"] >= 75 else "可用" if metadata["confidence"] >= 50 else "较低",
        "headline": headline,
        "summary": f"我们在多个划水和打腿时刻都观察到了这一点。{primary_summary}",
        "image": media_url,
        "metadata": metadata,
        "metrics": [
            {"label": "身体线偏差", "value": f"{line_deviation:.1f}", "unit": "°", "delta": "肩髋踝连线", "tone": "positive" if line_deviation < 8 else "warning"},
            {"label": "前伸宽度", "value": f"{reach_ratio:.2f}", "unit": "×肩宽", "delta": "由双腕距离计算", "tone": "positive" if 0.72 <= reach_ratio <= 1.55 else "warning"},
            {"label": "左右肘角差", "value": f"{elbow_difference:.1f}", "unit": "°", "delta": "同一采样帧", "tone": "positive" if elbow_difference < 12 else "warning"},
            {"label": "姿态覆盖", "value": f"{detection:.0f}", "unit": "%", "delta": "水面遮挡会影响", "tone": "positive" if detection >= 60 else "neutral"},
        ],
        "insights": [
            {"id": "reach", "title": headline, "summary": primary_summary, "impact": primary_impact, "action": primary_action, "successCue": primary_cue, "severity": severity, "timestamp": _format_timestamp(evidences["A"][0].timestamp), "marker": "A", "image": evidence_urls["A"]},
            {"id": "line", "title": "身体大部分时间能贴近水面" if line_deviation < 8 else "身体中段有明显下沉", "summary": "这个动作时刻，肩膀、髋部和脚没有朝同一个方向延伸，身体中间向下掉。" if line_deviation >= 8 else "这个动作时刻，从肩膀到脚能够保持舒展，身体比较贴近水面。", "impact": "身体下沉会增大迎水面积，每次划水都要先克服更多阻力。" if line_deviation >= 8 else "身体接近平直，同样的划水力量可以让你滑得更远。", "action": "下一趟只关注眼睛看池底、后脑勺放松，同时轻轻收紧腹部，让髋部靠近水面。", "successCue": "会感觉臀部更接近水面，脚后跟偶尔轻轻打到水面。", "severity": "good" if line_deviation < 8 else "observe", "timestamp": _format_timestamp(evidences["B"][0].timestamp), "marker": "B", "image": evidence_urls["B"]},
            {"id": "arms", "title": "两侧划水路径比较接近" if elbow_difference < 12 else "两只手臂的划水动作差得比较多", "summary": "这个动作时刻，一侧已经开始推水，另一侧还停在前伸位置，左右节奏没有接上。" if elbow_difference >= 12 else "这个动作时刻，两侧划水能够自然衔接，没有明显停顿。", "impact": "两侧动作不同会打乱划水节奏，一侧更容易提前疲劳。" if elbow_difference >= 12 else "两侧节奏接近，有利于保持直线前进。", "action": "做 4 组单臂自由泳，每侧 25 米，注意两边都先向前伸长，再用前臂把水向后推。", "successCue": "左右两侧每次划水的用力时间接近，身体不会突然向一边扭。", "severity": "good" if elbow_difference < 12 else "observe", "timestamp": _format_timestamp(evidences["C"][0].timestamp), "marker": "C", "image": evidence_urls["C"]},
            {"id": "kick", "title": "打腿幅度比较轻松" if knee_flexion < 35 else "打腿时膝盖弯得太多", "summary": "这个动作时刻，小腿从膝盖后方向下甩，像在踩水，而不是整条腿从髋部带动。" if knee_flexion >= 35 else "这个动作时刻，腿部能够从髋部带动，膝盖没有明显折起。", "impact": "膝盖弯得太多会让大腿迎水，阻力增加，还会消耗更多体力。" if knee_flexion >= 35 else "小幅打腿能减少阻力，也更容易保持身体平稳。", "action": "做 4 组 20 秒扶板打腿，脚踝放松，只让大腿从髋部小幅上下摆动。", "successCue": "水花集中在脚边，膝盖不会频繁露出水面，腿部感觉轻而连续。", "severity": "good" if knee_flexion < 35 else "observe", "timestamp": _format_timestamp(evidences["D"][0].timestamp), "marker": "D", "image": evidence_urls["D"]},
        ],
        "fileName": file_name,
    }


def analyze_video(
    video_path: Path,
    sport: str,
    report_id: str,
    file_name: str,
    output_path: Path,
    media_url: str,
    progress: ProgressCallback,
) -> dict:
    pose_frames, metadata = _extract_pose_frames(video_path, progress)
    body_axis_angle = _body_axis_angle_from_horizontal(pose_frames)
    metadata["bodyAxisAngleFromHorizontal"] = body_axis_angle
    if sport == "running" and body_axis_angle < 30:
        raise AnalysisError("SPORT_MISMATCH", "画面中的身体长期接近水平，更像游泳视频。请切换到游泳后重新分析。")
    if sport == "swimming" and body_axis_angle > 55:
        raise AnalysisError("SPORT_MISMATCH", "画面中的身体长期接近直立，更像跑步视频。请切换到跑步后重新分析。")
    progress(82, "计算专项动作指标")
    if sport == "running":
        report = _running_report(video_path, report_id, file_name, pose_frames, metadata, media_url, output_path)
    elif sport == "swimming":
        report = _swimming_report(video_path, report_id, file_name, pose_frames, metadata, media_url, output_path)
    else:
        raise AnalysisError("SPORT_NOT_SUPPORTED", "当前只支持跑步和游泳。")
    progress(96, "生成真实证据帧")
    return report
