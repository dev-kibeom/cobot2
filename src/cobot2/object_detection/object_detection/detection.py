import os
import cv2
import json
import rclpy
import time
import numpy as np
from datetime import datetime

from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor
from ament_index_python.packages import get_package_share_directory

from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String
from od_msg.srv import GetTargetPose
from object_detection.realsense import ImgNode
from object_detection.yolo import YoloModel

PACKAGE_NAME = 'object_detection'
PACKAGE_PATH = get_package_share_directory(PACKAGE_NAME)

class ObjectDetection(Node):
    def __init__(self):
        super().__init__('object_detection')
        
        self._init_parameters()
        self._init_components()
        self._init_ros_interfaces()
        
        self.get_logger().info("👁️ Vision AI Node initialized (Refactored & Clean).")

    # ==========================================================
    # 1. 초기화 (Initialization) 블록
    # ==========================================================
    def _init_parameters(self):
        """파라미터 및 디렉토리 설정"""
        self.save_dir = os.path.join(os.path.expanduser('~'), 'cobot_ws', 'vision_logs')
        os.makedirs(self.save_dir, exist_ok=True)
        
        self.declare_parameter('model_name', 'yolo')
        self.declare_parameter('yolo_model_filename', 'best.pt')
        self.declare_parameter('yolo_class_name_json', 'class_name.json')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.5)

    def _init_components(self):
        """비전 AI 및 카메라 컴포넌트 로드"""
        model_name = self.get_parameter('model_name').value
        model_file = self.get_parameter('yolo_model_filename').value
        json_file = self.get_parameter('yolo_class_name_json').value
        conf_thr = self.get_parameter('confidence_threshold').value
        iou_thr = self.get_parameter('iou_threshold').value
        
        self.img_node = ImgNode()
        self.intrinsics = None
        self.bridge = CvBridge()
        
        if model_name.lower() == 'yolo':
            self.model = YoloModel(model_file, json_file, conf_thr, iou_thr)
        else:
            raise ValueError(f"Unsupported model: {model_name}")

    def _init_ros_interfaces(self):
        """ROS 2 퍼블리셔, 서비스, 타이머 설정"""
        self.create_service(GetTargetPose, '/get_3d_position', self.handle_get_depth)
        
        self.last_color_vis = None 
        self.last_depth_vis = None
        
        self.annotated_pub = self.create_publisher(CompressedImage, '/detection/annotated_image/compressed', 10)
        self.depth_vis_pub = self.create_publisher(CompressedImage, '/detection/depth_visual/compressed', 10)
        self.detection_pub = self.create_publisher(String, '/detection', 10)
        self.snapshot_timer = self.create_timer(1.0, self.publish_snapshot_loop)

    # ==========================================================
    # 2. 핵심 로직 (Core Logic) 블록
    # ==========================================================
    def handle_get_depth(self, request, response):
        """클라이언트 요청을 받아 탐지를 수행하고 결과를 반환"""
        target_name = request.target_name
        self.get_logger().info(f"🔍 탐지 요청 수신: '{target_name}'")

        coords = self._compute_position(target_name)

        if coords != (0.0, 0.0, 0.0):
            response.success = True
            response.position = [float(x) for x in coords]
            response.message = "Detection successful"
            self.get_logger().info(f"✅ 탐지 성공! 3D 좌표: {response.position}")
        else:
            response.success = False
            response.position = [0.0, 0.0, 0.0]
            response.message = f"Failed to detect '{target_name}'"
            self.get_logger().warn(f"❌ 탐지 실패: '{target_name}'")

        return response

    def _compute_position(self, target):
        """탐지 및 3D 카메라 좌표 계산"""
        if self.intrinsics is None:
            self.intrinsics = self._wait_for_valid_data(self.img_node.get_camera_intrinsic, "camera intrinsics")
            
        box, score = self.model.get_best_detection(self.img_node, target)
        color_frame = self.img_node.get_color_frame()
        depth_frame = self.img_node.get_depth_frame()

        # 탐지 실패 시
        if box is None or score is None:
            self._process_visuals(color_frame, depth_frame, None, target, None, None)
            self._publish_detection(target, None, 0.0, None)
            return 0.0, 0.0, 0.0

        # 탐지 성공 시 좌표 계산
        cx, cy = map(int, [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        cz = self._get_depth(cx, cy)

        if cz <= 0:
            self.get_logger().warn("⚠️ 깊이(Depth) 값이 범위를 벗어났습니다.")
            self._process_visuals(color_frame, depth_frame, box, target, score, None)
            self._publish_detection(target, box, score, None)
            return 0.0, 0.0, 0.0

        coords = self._pixel_to_camera_coords(cx, cy, cz)
        self._process_visuals(color_frame, depth_frame, box, target, score, coords)
        self._publish_detection(target, box, score, coords)

        return coords

    # ==========================================================
    # 3. 데이터 처리 및 시각화 (Vision Math & Visuals) 블록
    # ==========================================================
    def _get_depth(self, x, y):
        """중심점 주변 10x10 영역의 유효한 Depth 중앙값 추출"""
        frame = self._wait_for_valid_data(self.img_node.get_depth_frame, "depth frame")
        try:
            h, w = frame.shape
            patch = frame[max(0, y-5):min(h, y+5), max(0, x-5):min(w, x+5)]
            valid_depths = patch[patch > 0]
            return float(np.median(valid_depths)) if len(valid_depths) > 0 else 0.0
        except Exception:
            return 0.0

    def _pixel_to_camera_coords(self, x, y, z):
        """2D 픽셀 -> 3D 공간 좌표 변환"""
        return (
            (x - self.intrinsics['ppx']) * z / self.intrinsics['fx'],
            (y - self.intrinsics['ppy']) * z / self.intrinsics['fy'],
            z
        )

    def _process_visuals(self, color_frame, depth_frame, box, target, score, coords):
        """시각화 생성, 로컬 저장 및 퍼블리시용 변수 갱신"""
        if color_frame is None: return
        
        vis = color_frame.copy()
        depth_vis = None
        
        # 🚨 [중요 버그 수정] Depth 아웃라이어 제거 (0~2000mm) 후 정규화
        if depth_frame is not None:
            depth_clipped = np.clip(depth_frame, 0, 2000)
            depth_norm = cv2.normalize(depth_clipped, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            depth_vis = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        
        # 박스 및 텍스트 그리기
        if box is not None and score is not None:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (79, 131, 244), 2)
            
            label = f"{target} {score:.2f}"
            if coords is not None:
                label += f" | X:{coords[0]:.0f} Y:{coords[1]:.0f} Z:{coords[2]:.0f}"
                if depth_vis is not None:
                    cv2.rectangle(depth_vis, (x1, y1), (x2, y2), (255, 255, 255), 2)
                    cv2.circle(depth_vis, (int((x1+x2)/2), int((y1+y2)/2)), 5, (0, 0, 255), -1)

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw + 4, y1), (79, 131, 244), -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 4), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # 파일 저장
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:15]
        cv2.imwrite(os.path.join(self.save_dir, f"{ts}_{target}_color.jpg"), vis)
        if depth_vis is not None:
            cv2.imwrite(os.path.join(self.save_dir, f"{ts}_{target}_depth.jpg"), depth_vis)
        
        # ROS 퍼블리시 상태 업데이트
        self.last_color_vis = vis
        self.last_depth_vis = depth_vis

    def _publish_detection(self, target, box, score, coords):
        """/detection 토픽에 탐지 결과를 JSON String으로 발행"""
        payload = {
            'object_name': target,
            'detected':    coords is not None,
            'confidence':  round(float(score), 4) if score is not None else 0.0,
            'bbox':        [round(float(v), 1) for v in box] if box is not None else None,
            'position':    [round(float(v), 4) for v in coords] if coords is not None else None,
        }
        msg = String()
        msg.data = json.dumps(payload, ensure_ascii=False)
        self.detection_pub.publish(msg)

    # ==========================================================
    # 4. 유틸리티 (Utility) 블록
    # ==========================================================
    def publish_snapshot_loop(self):
        """1초 주기로 최신 이미지를 ROS Topic으로 송출"""
        try:
            if self.last_color_vis is not None:
                self.annotated_pub.publish(self.bridge.cv2_to_compressed_imgmsg(self.last_color_vis))
            if self.last_depth_vis is not None:
                self.depth_vis_pub.publish(self.bridge.cv2_to_compressed_imgmsg(self.last_depth_vis))
        except Exception:
            pass

    def _wait_for_valid_data(self, getter, description):
        """센서 데이터가 준비될 때까지 대기"""
        data = getter()
        while data is None or (isinstance(data, np.ndarray) and not data.any()):
            time.sleep(0.1)
            self.get_logger().info(f"⏳ {description} 데이터 대기 중...")
            data = getter()
        return data

def main(args=None):
    rclpy.init(args=args)
    node = ObjectDetection()
    
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    executor.add_node(node.img_node)
    
    try:
        executor.spin()
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()