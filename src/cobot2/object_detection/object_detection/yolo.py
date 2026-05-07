########## YoloModel ##########
import os
import json
import time
from collections import Counter

import rclpy
from ament_index_python.packages import get_package_share_directory
from ultralytics import YOLO
import numpy as np


PACKAGE_NAME = "object_detection"
PACKAGE_PATH = get_package_share_directory(PACKAGE_NAME)

YOLO_MODEL_FILENAME = "best.pt"
YOLO_CLASS_NAME_JSON = "class_name.json"

YOLO_MODEL_PATH = os.path.join(PACKAGE_PATH, "resource", YOLO_MODEL_FILENAME)
YOLO_JSON_PATH = os.path.join(PACKAGE_PATH, "resource", YOLO_CLASS_NAME_JSON)


class YoloModel:
    def __init__(self, model_filename, json_filename, conf_thres, iou_thres):
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres
        
        package_path = get_package_share_directory("object_detection")
        model_path = os.path.join(package_path, "resource", model_filename)
        json_path = os.path.join(package_path, "resource", json_filename)
        
        self.model = YOLO(model_path)
        with open(YOLO_JSON_PATH, "r", encoding="utf-8") as file:
            class_dict = json.load(file)
            self.reversed_class_dict = {v: int(k) for k, v in class_dict.items()}

    def get_frames(self, img_node, target_count=5, timeout=2.0):
        """
        정확히 서로 다른 'target_count' 장의 프레임을 모읍니다.
        timeout 시간이 지나면 모인 만큼만 반환합니다.
        """
        
        frames = {}
        end_time = time.time() + timeout

        while len(frames) < target_count and time.time() < end_time:
            # 큐에 쌓인 콜백을 처리 (timeout 0.1초 주어 CPU 점유율 하락 방지)
            rclpy.spin_once(img_node, timeout_sec=0.1)
            
            frame = img_node.get_color_frame()
            stamp = img_node.get_color_frame_stamp()
            
            # 유효한 프레임이고 이전과 똑같은 타임스탬프가 아닌 경우에만
            if frame is not None and stamp not in frames:
                frames[stamp] = frame
            
            # time.sleep(0.01) -> 기존의 인자없는 논블로킹 spin_once와 강제휴식

        if not frames:
            print(f"No frames captured within {timeout} seconds.")

        print(f"Captured {len(frames)} valid frames.")
        return list(frames.values())

    def get_best_detection(self, img_node, target):
        rclpy.spin_once(img_node)
        frames = self.get_frames(img_node)
        if not frames:  # Check if frames are empty
            return None

        results = self.model(frames, verbose=False)
        print("classes: ")
        print(results[0].names)
        detections = self._aggregate_detections(results)
        
        label_id = self.reversed_class_dict.get(target)
        
        if label_id is None:
            print(f"⚠️ 비전 에러: '{target}'은(는) JSON 파일에 등록되지 않은 물체입니다.")
            return None, None
        
        print("label_id: ", label_id)
        print("detections: ", detections)

        matches = [d for d in detections if d["label"] == label_id]
        if not matches:
            print("No matches found for the target label.")
            return None, None
        best_det = max(matches, key=lambda x: x["score"])
        return best_det["box"], best_det["score"]

    def _aggregate_detections(self, results):
        """
        Fuse raw detection boxes across frames using IoU-based grouping
        and majority voting for robust final detections.
        """
        raw = []
        for res in results:
            for box, score, label in zip(
                res.boxes.xyxy.tolist(),
                res.boxes.conf.tolist(),
                res.boxes.cls.tolist(),
            ):
                if score >= self.conf_thres:
                    raw.append({"box": box, "score": score, "label": int(label)})

        final = []
        used = [False] * len(raw)

        for i, det in enumerate(raw):
            if used[i]:
                continue
            group = [det]
            used[i] = True
            for j, other in enumerate(raw):
                if not used[j] and other["label"] == det["label"]:
                    if self._iou(det["box"], other["box"]) >= self.iou_thres:
                        group.append(other)
                        used[j] = True

            boxes = np.array([g["box"] for g in group])
            scores = np.array([g["score"] for g in group])
            labels = [g["label"] for g in group]

            final.append(
                {
                    "box": boxes.mean(axis=0).tolist(),
                    "score": float(scores.mean()),
                    "label": Counter(labels).most_common(1)[0][0],
                }
            )

        return final

    def _iou(self, box1, box2):
        """
        Compute Intersection over Union (IoU) between two boxes [x1, y1, x2, y2].
        """
        x1, y1 = max(box1[0], box2[0]), max(box1[1], box2[1])
        x2, y2 = min(box1[2], box2[2]), min(box1[3], box2[3])
        inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
        area1 = (box1[2] - box1[0]) * (box1[3] - box1[1])
        area2 = (box2[2] - box2[0]) * (box2[3] - box2[1])
        union = area1 + area2 - inter
        return inter / union if union > 0 else 0.0
