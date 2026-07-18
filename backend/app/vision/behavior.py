"""Camera based behavior analysis using MediaPipe face landmarks.

Each frame produces gaze, blink, head pose and expression signals which
are aggregated into a rolling confidence estimate. Returns None per
frame when mediapipe or opencv are not installed.
"""

import base64
from typing import Optional

import numpy as np

LEFT_EYE = [33, 160, 158, 133, 153, 144]
RIGHT_EYE = [362, 385, 387, 263, 373, 380]
LEFT_IRIS = [468, 469, 470, 471, 472]
RIGHT_IRIS = [473, 474, 475, 476, 477]
MOUTH = [61, 291, 13, 14]

_face_mesh = None
_cv2 = None


def vision_available() -> bool:
    try:
        import cv2  # noqa: F401
        import mediapipe  # noqa: F401
        return True
    except ImportError:
        return False


def _get_mesh():
    global _face_mesh, _cv2
    if _face_mesh is None:
        import cv2
        import mediapipe as mp
        _cv2 = cv2
        _face_mesh = mp.solutions.face_mesh.FaceMesh(
            max_num_faces=1, refine_landmarks=True,
            min_detection_confidence=0.5, min_tracking_confidence=0.5,
        )
    return _face_mesh


def _ear(points: np.ndarray) -> float:
    """Eye aspect ratio, low values mean the eye is closed."""
    a = np.linalg.norm(points[1] - points[5])
    b = np.linalg.norm(points[2] - points[4])
    c = np.linalg.norm(points[0] - points[3])
    return float((a + b) / (2.0 * c + 1e-6))


def _gaze_offset(landmarks: np.ndarray, eye_idx: list[int], iris_idx: list[int]) -> float:
    """Horizontal iris position within the eye, 0 is centered."""
    eye = landmarks[eye_idx]
    iris = landmarks[iris_idx].mean(axis=0)
    inner, outer = eye[3], eye[0]
    width = np.linalg.norm(outer[:2] - inner[:2]) + 1e-6
    center = (inner[:2] + outer[:2]) / 2
    return float((iris[0] - center[0]) / width)


class BehaviorAnalyzer:
    """Tracks per frame signals for one session and aggregates them."""

    def __init__(self):
        self.samples: list[dict] = []
        self.blinks = 0
        self._eye_closed = False

    def analyze_frame(self, jpeg_b64: str) -> Optional[dict]:
        """Analyze one webcam frame, returns the extracted signals."""
        if not vision_available():
            return None
        mesh = _get_mesh()
        cv2 = _cv2
        raw = base64.b64decode(jpeg_b64.split(",")[-1])
        img = cv2.imdecode(np.frombuffer(raw, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        result = mesh.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
        if not result.multi_face_landmarks:
            sample = {"face": False}
            self.samples.append(sample)
            return sample

        pts = np.array([[lm.x * w, lm.y * h, lm.z * w] for lm in result.multi_face_landmarks[0].landmark])

        ear = (_ear(pts[LEFT_EYE]) + _ear(pts[RIGHT_EYE])) / 2
        closed = ear < 0.18
        if closed and not self._eye_closed:
            self.blinks += 1
        self._eye_closed = closed

        gaze_x = (_gaze_offset(pts, LEFT_EYE, LEFT_IRIS) + _gaze_offset(pts, RIGHT_EYE, RIGHT_IRIS)) / 2

        # Rough head pose from landmark geometry: nose vs face box.
        nose = pts[1]
        left_face, right_face = pts[234], pts[454]
        chin, forehead = pts[152], pts[10]
        yaw = float((nose[0] - (left_face[0] + right_face[0]) / 2) /
                    (abs(right_face[0] - left_face[0]) + 1e-6))
        pitch = float((nose[1] - (forehead[1] + chin[1]) / 2) /
                      (abs(chin[1] - forehead[1]) + 1e-6))

        mouth = pts[MOUTH]
        mouth_open = float(np.linalg.norm(mouth[2] - mouth[3]) /
                           (np.linalg.norm(mouth[0] - mouth[1]) + 1e-6))
        smile = float(np.linalg.norm(mouth[0][:2] - mouth[1][:2]) /
                      (np.linalg.norm(right_face[:2] - left_face[:2]) + 1e-6))

        eye_contact = abs(gaze_x) < 0.12 and abs(yaw) < 0.18 and abs(pitch) < 0.25 and not closed

        sample = {
            "face": True,
            "eye_contact": bool(eye_contact),
            "gaze_x": round(gaze_x, 3),
            "yaw": round(yaw, 3),
            "pitch": round(pitch, 3),
            "ear": round(ear, 3),
            "smile": round(smile, 3),
            "mouth_open": round(mouth_open, 3),
        }
        self.samples.append(sample)
        return sample

    def summary(self) -> dict:
        """Aggregate all frames into session level behavior metrics."""
        faced = [s for s in self.samples if s.get("face")]
        if not faced:
            return {"frames": len(self.samples), "face_visible_pct": 0.0, "available": vision_available()}

        contact_pct = 100.0 * sum(1 for s in faced if s.get("eye_contact")) / len(faced)
        yaws = np.array([s["yaw"] for s in faced])
        pitches = np.array([s["pitch"] for s in faced])
        head_stability = float(max(0.0, 1.0 - 3.0 * (np.std(yaws) + np.std(pitches))))
        smile_avg = float(np.mean([s["smile"] for s in faced]))

        # Simple weighted blend, meant as a coaching signal not a judgment.
        confidence = (
            0.45 * min(contact_pct / 70.0, 1.0)
            + 0.35 * head_stability
            + 0.20 * min(max((smile_avg - 0.30) / 0.15, 0.0), 1.0)
        )

        return {
            "available": True,
            "frames": len(self.samples),
            "face_visible_pct": round(100.0 * len(faced) / len(self.samples), 1),
            "eye_contact_pct": round(contact_pct, 1),
            "head_stability": round(head_stability, 2),
            "avg_smile": round(smile_avg, 3),
            "blinks": self.blinks,
            "confidence_score": round(100 * confidence, 1),
        }
