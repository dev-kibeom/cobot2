import os
import cv2
import rclpy
import time
import threading
import numpy as np
from datetime import datetime

from cv_bridge import CvBridge
from rclpy.node import Node
from rclpy.executors import MultiThreadedExecutor

from ament_index_python.packages import get_package_share_directory

from sensor_msgs.msg import Image, CompressedImage
from od_msg.srv import GetTargetPose
from object_detection.realsense import ImgNode
from object_detection.yolo import YoloModel


PACKAGE_NAME = 'object_detection'
PACKAGE_PATH = get_package_share_directory(PACKAGE_NAME)


class ObjectDetection(Node):
    def __init__(self, model_name = 'yolo'):
        super().__init__('object_detection')
        
        self.save_dir = os.path.join(os.path.expanduser('~'), 'cobot_ws', 'vision_logs')
        os.makedirs(self.save_dir, exist_ok=True)
        
        self.declare_parameter('model_name', 'yolo')
        self.declare_parameter('yolo_model_filename', 'best.pt')
        self.declare_parameter('yolo_class_name_json', 'class_name.json')
        self.declare_parameter('confidence_threshold', 0.5)
        self.declare_parameter('iou_threshold', 0.5)
        
        model_name = self.get_parameter('model_name').value
        self.model_filename = self.get_parameter('yolo_model_filename').value
        self.json_filename = self.get_parameter('yolo_class_name_json').value
        self.conf_threshold = self.get_parameter('confidence_threshold').value
        self.iou_threshold = self.get_parameter('iou_threshold').value
        
        self.img_node = ImgNode()
        self.model = self._load_model(model_name)
        
        self.intrinsics = None
        
        self.create_service(
            GetTargetPose,
            '/get_3d_position',
            self.handle_get_depth
        )

        self.bridge = CvBridge()
        
        self.last_snapshot = None 
        self.annotated_pub = self.create_publisher(CompressedImage, '/detection/annotated_image/compressed', 10)
        self.depth_vis_pub = self.create_publisher(CompressedImage, '/detection/depth_visual/compressed', 10)
        self.snapshot_timer = self.create_timer(1.0, self.publish_snapshot_loop)
         
        self.get_logger().info("👁️ Vision AI Node initialized (JIT Mode).")

    def _load_model(self, name):
        """모델 이름에 따라 인스턴스를 반환합니다."""
        if name.lower() == 'yolo':
            return YoloModel(self.model_filename, self.json_filename, 
                             self.conf_threshold, self.iou_threshold)
        raise ValueError(f"Unsupported model: {name}")

    def handle_get_depth(self, request, response):
        """클라이언트(ActionManager)의 JIT 요청을 처리해 3D 좌표를 반환합니다."""
        
        target_name = request.target_name
        self.get_logger().info(f"🔍 탐지 요청 수신: '{target_name}'")

        coords = self._compute_position(target_name)

        # 응답(success, position, message) 작성
        if coords != (0.0, 0.0, 0.0):
            response.success = True
            response.position = [float(x) for x in coords]
            response.message = "Detection successful"
            self.get_logger().info(f"✅ 탐지 성공! 카메라 좌표: {response.position}")
        else:
            response.success = False
            response.position = [0.0, 0.0, 0.0]
            response.message = f"Failed to detect '{target_name}'"
            self.get_logger().warn(f"❌ 탐지 실패: '{target_name}'")

        return response

    def _compute_position(self, target):
        """이미지를 처리해 객체의 카메라 좌표를 계산하고 화면에 출력합니다."""
        # 1. 카메라 내부 파라미터가 없으면 가져옵니다.
        if self.intrinsics is None:
            self.intrinsics = self._wait_for_valid_data(
                self.img_node.get_camera_intrinsic, "camera intrinsics"
            )
            
        # 2. YOLO 탐지 및 최신 프레임 획득
        box, score = self.model.get_best_detection(self.img_node, target)
        current_frame = self.img_node.get_color_frame()
        depth_frame = self.img_node.get_depth_frame()

        # 3. 탐지 실패 시 빈 화면 저장 후 종료
        if box is None or score is None:
            self.get_logger().warn(f"'{target}'을(를) 화면에서 찾을 수 없습니다.")
            self._push_display_and_save(current_frame, depth_frame, None, target, None, None)
            return 0.0, 0.0, 0.0
        
        # 4. 탐지 성공 시 중심점(cx, cy) 추출 및 깊이(cz) 획득
        self.get_logger().info(f"Detection: box={box}, score={score:.2f}")
        cx, cy = map(int, [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        cz = self._get_depth(cx, cy)

        if cz is None or cz <= 0:
            self.get_logger().warn("깊이(Depth) 값이 범위를 벗어났거나 유효하지 않습니다.")
            self._push_display_and_save(current_frame, depth_frame, box, target, score, None)
            return 0.0, 0.0, 0.0

        # 5. 픽셀 좌표를 3D 카메라 좌표로 변환 후 저장
        coords = self._pixel_to_camera_coords(cx, cy, cz)
        self._push_display_and_save(current_frame, depth_frame, box, target, score, coords)

        return coords

    def _get_depth(self, x, y):
        """픽셀 주변 10x10 영역의 유효한 depth 중앙값을 구합니다."""
        frame = self._wait_for_valid_data(self.img_node.get_depth_frame, "depth frame")
        try:
            h, w = frame.shape
            x_min, x_max = max(0, x - 5), min(w, x + 5)
            y_min, y_max = max(0, y - 5), min(h, y + 5)
            patch = frame[y_min:y_max, x_min:x_max]
            valid_depths = patch[patch > 0]
            
            if len(valid_depths) > 0:
                return float(np.median(valid_depths))
            else:
                return 0.0
        except Exception as e:
            self.get_logger().warn(f"깊이값 계산 에러: {e}")
            return 0.0

    def _wait_for_valid_data(self, getter, description):
        """getter 함수가 유효한 데이터를 반환할 때까지 spin 하며 재시도합니다."""
        data = getter()
        while data is None or (isinstance(data, np.ndarray) and not data.any()):
            # rclpy.spin_once(self.img_node)
            time.sleep(0.1)
            self.get_logger().info(f"Retry getting {description}.")
            data = getter()
        return data

    def _pixel_to_camera_coords(self, x, y, z):
        """픽셀 좌표와 intrinsics를 이용해 카메라 좌표계로 변환합니다."""
        fx = self.intrinsics['fx']
        fy = self.intrinsics['fy']
        ppx = self.intrinsics['ppx']
        ppy = self.intrinsics['ppy']
        return (
            (x - ppx) * z / fx,
            (y - ppy) * z / fy,
            z
        )

    def _push_display_and_save(self, color_frame, depth_frame, box, target, score, coords):
        """BBox 및 좌표를 그리고 이미지를 저장/퍼블리시 합니다."""
        if color_frame is None:
            return
        
        vis = color_frame.copy()
        depth_vis = None
        
        # 16비트 Depth를 화려한 컬러맵(8비트)으로 변환
        if depth_frame is not None:
            # 0~65535 데이터를 눈으로 보기 좋게 0~255로 정규화
            depth_norm = cv2.normalize(depth_frame, None, 0, 255, cv2.NORM_MINMAX, dtype=cv2.CV_8U)
            depth_vis = cv2.applyColorMap(depth_norm, cv2.COLORMAP_JET)
        
        # BBox 및 텍스트 오버레이
        if box is not None and score is not None:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (79, 131, 244), 2)
            
            # 레이블에 모델 스코어 추가
            label = f"{target} {score:.2f}"
            
            # 좌표가 있으면 레이블에 추가
            if coords is not None:
                cx, cy, cz = coords
                label += f" | X:{cx:.1f} Y:{cy:.1f} Z:{cz:.1f}"
                # 깊이 이미지에도 박스 그리기
                if depth_vis is not None:
                    cv2.rectangle(depth_vis, (x1, y1), (x2, y2), (255, 255, 255), 2)
                    cv2.circle(depth_vis, (int((x1+x2)/2), int((y1+y2)/2)), 5, (0, 0, 255), -1)

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw + 4, y1), (79, 131, 244), -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        # 결과 저장 (타임스탬프 활용)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:19]
        color_filename = os.path.join(self.save_dir, f"detect_{timestamp}_{target}_color.jpg")
        cv2.imwrite(color_filename, vis)
        
        if depth_vis is not None:
            depth_filename = os.path.join(self.save_dir, f"detect_{timestamp}_{target}_depth.jpg")
            cv2.imwrite(depth_filename, depth_vis)
        
        # ROS 퍼블리시를 위한 변수 업데이트
        self.last_snapshot = vis
        self.last_depth_snapshot = depth_vis
        
        try:
            img_msg = self.bridge.cv2_to_compressed_imgmsg(vis)
            self.annotated_pub.publish(img_msg)
            
            if depth_vis is not None:
                depth_msg = self.bridge.cv2_to_compressed_imgmsg(depth_vis)
                self.depth_vis_pub.publish(depth_msg)
        except Exception as e:
            self.get_logger().error(f"이미지 토픽 발행 실패: {e}")
    
    def publish_snapshot_loop(self):
        """1초에 1번씩 최근 스냅샷을 유지 송출 (rqt 늦게 켜도 보이도록 방어)"""
        try:
            if self.last_snapshot is not None:
                img_msg = self.bridge.cv2_to_compressed_imgmsg(self.last_snapshot)
                self.annotated_pub.publish(img_msg)
            if self.last_depth_snapshot is not None:
                depth_msg = self.bridge.cv2_to_compressed_imgmsg(self.last_depth_snapshot)
                self.depth_vis_pub.publish(depth_msg)
        except Exception:
            pass

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
