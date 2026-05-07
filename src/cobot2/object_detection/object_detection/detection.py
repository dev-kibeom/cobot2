import cv2
import rclpy
import numpy as np
from rclpy.node import Node
from typing import Any, Callable, Optional, Tuple

from ament_index_python.packages import get_package_share_directory
from od_msg.srv import GetTargetPose
from object_detection.realsense import ImgNode
from object_detection.yolo import YoloModel


PACKAGE_NAME = 'object_detection'
PACKAGE_PATH = get_package_share_directory(PACKAGE_NAME)


class ObjectDetectionNode(Node):
    def __init__(self, model_name = 'yolo'):
        super().__init__('object_detection_node')
        self.img_node = ImgNode()
        self.model = self._load_model(model_name)
        self.intrinsics = self._wait_for_valid_data(
            self.img_node.get_camera_intrinsic, "camera intrinsics"
        )
        self.create_service(
            GetTargetPose,
            '/get_3d_position',
            self.handle_get_depth
        )

        self.get_logger().info("👁️ Vision AI Node initialized (JIT Mode).")

    def _load_model(self, name):
        """모델 이름에 따라 인스턴스를 반환합니다."""
        if name.lower() == 'yolo':
            return YoloModel()
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
        """이미지를 처리해 객체의 카메라 좌표를 계산합니다."""
        rclpy.spin_once(self.img_node)

        box, score = self.model.get_best_detection(self.img_node, target)
        if box is None or score is None:
            self.get_logger().warn("No detection found.")
            return 0.0, 0.0, 0.0
        
        self.get_logger().info(f"Detection: box={box}, score={score}")
        cx, cy = map(int, [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        cz = self._get_depth(cx, cy)

        if cz is None or cz <= 0:
            self.get_logger().warn("Depth out of range or invalid.")
            return 0.0, 0.0, 0.0

        return self._pixel_to_camera_coords(cx, cy, cz)

    def _get_depth(self, x, y):
        """픽셀 좌표의 depth 값을 안전하게 읽어옵니다."""
        frame = self._wait_for_valid_data(self.img_node.get_depth_frame, "depth frame")
        try:
            return frame[y, x]
        except IndexError:
            self.get_logger().warn(f"Coordinates ({x},{y}) out of range.")
            return None

    def _wait_for_valid_data(self, getter, description):
        """getter 함수가 유효한 데이터를 반환할 때까지 spin 하며 재시도합니다."""
        data = getter()
        while data is None or (isinstance(data, np.ndarray) and not data.any()):
            rclpy.spin_once(self.img_node)
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

    def _compute_position(self, target):
        """이미지를 처리해 객체의 카메라 좌표를 계산하고 화면에 출력합니다."""
        rclpy.spin_once(self.img_node)

        box, score = self.model.get_best_detection(self.img_node, target)
        
        # 화면 시각화를 위해 최신 컬러 프레임을 가져옵니다.
        frame = self.img_node.get_color_frame()

        if box is None or score is None:
            self.get_logger().warn("No detection found.")
            # 객체를 못 찾았더라도 현재 카메라는 계속 보여주도록 창을 갱신합니다.
            if frame is not None:
                cv2.imshow("Vision AI - Target Detection", frame)
                cv2.waitKey(1)
            return 0.0, 0.0, 0.0
        
        self.get_logger().info(f"Detection: box={box}, score={score}")
        cx, cy = map(int, [(box[0] + box[2]) / 2, (box[1] + box[3]) / 2])
        
        # ==========================================
        # 🎨 OpenCV 시각화 그리기 영역
        # ==========================================
        # if frame is not None:
        #     # 1. 경계 박스 그리기 (파란색, 두께 2)
        #     x1, y1, x2, y2 = map(int, box)
        #     cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 0, 0), 2)
            
        #     # 2. 중심점 타겟팅 그리기 (빨간색 점)
        #     cv2.circle(frame, (cx, cy), 5, (0, 0, 255), -1)
            
        #     # 3. 객체 이름과 정확도(Score) 텍스트 쓰기
        #     text = f"{target} ({score:.2f})"
        #     cv2.putText(frame, text, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
            
        #     # 4. 윈도우 창에 이미지 출력
        #     cv2.imshow("Vision AI - Target Detection", frame)
        #     cv2.waitKey(1) # 화면을 갱신하기 위한 필수 대기 시간
        # ==========================================

        cz = self._get_depth(cx, cy)

        if cz is None or cz <= 0:
            self.get_logger().warn("Depth out of range or invalid.")
            return 0.0, 0.0, 0.0

        return self._pixel_to_camera_coords(cx, cy, cz)

def main(args=None):
    rclpy.init(args=args)
    node = ObjectDetectionNode()
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
