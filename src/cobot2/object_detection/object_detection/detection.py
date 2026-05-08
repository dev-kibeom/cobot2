import cv2
import rclpy
import time
import threading
import numpy as np
import urllib.request

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

    def _compute_position(self, target):
        """이미지를 처리해 객체의 카메라 좌표를 계산하고 화면에 출력합니다."""
        #rclpy.spin_once(self.img_node)

        # 처음 탐지를 시도할 때, 카메라 파라미터가 비어있으면 그때 딱 한 번만 가져옵니다.
        if self.intrinsics is None:
            self.get_logger().info("카메라 내부 파라미터(Intrinsics)를 로드합니다...")
            self.intrinsics = self._wait_for_valid_data(
                self.img_node.get_camera_intrinsic, "camera intrinsics"
            )
            
        box, score = self.model.get_best_detection(self.img_node, target)
        
        # 탐지가 끝난 직후, 현재 프레임을 가져와 딱 한 번만 박스를 그리고 송출합니다.
        current_frame = self.img_node.get_color_frame()
        self._push_display_frame(current_frame, box, target, score)

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

    def _push_display_frame(self, frame, box, target, score,
                            url='http://localhost:8000/admin/display/frame'):
        """bbox 오버레이한 프레임을 Manager UI display API로 push."""
        if frame is None:
            return
        
        vis = frame.copy()
        if box is not None and score is not None:
            x1, y1, x2, y2 = map(int, box)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (79, 131, 244), 2)
            label = f"{target} {score:.2f}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(vis, (x1, y1 - th - 8), (x1 + tw + 4, y1), (79, 131, 244), -1)
            cv2.putText(vis, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        
        self.last_snapshot = vis
        
        # ROS rqt용 토픽 발행 (cv2 이미지를 ROS Image 메시지로 변환)
        try:
            img_msg = self.bridge.cv2_to_compressed_imgmsg(vis)
            self.annotated_pub.publish(img_msg)
        except Exception as e:
            self.get_logger().error(f"이미지 토픽 발행 실패: {e}")
            
        # 웹 서버 HTTP 전송 (ROS 스레드를 막지 않도록 파이썬 백그라운드 스레드로 격리)
        # def send_to_web():
        #     try:
        #         _, buf = cv2.imencode('.jpg', vis, [cv2.IMWRITE_JPEG_QUALITY, 80])
        #         req = urllib.request.Request(
        #             url, data=buf.tobytes(),
        #             headers={'Content-Type': 'image/jpeg'},
        #         )
        #         # 타임아웃을 0.5초로 줄여 백그라운드 스레드도 금방 사라지게 합니다.
        #         urllib.request.urlopen(req, timeout=0.5) 
        #     except Exception:
        #         pass
    
        # threading.Thread(target=send_to_web, daemon=True).start()
        
    # def publish_live_stream(self):
    #     """타이머에 의해 0.1초마다 끊임없이 카메라 화면을 ROS rqt로 송출합니다."""
    #     frame = self.img_node.get_color_frame()
    #     if frame is not None:
    #         # 마지막으로 기억된 타겟(latest_box)이 있다면 계속 화면에 그려줍니다.
    #         self._push_display_frame(frame, self.latest_box, self.latest_target, self.latest_score)
    
    def publish_snapshot_loop(self):
        """1초에 1번씩 최근 스냅샷을 유지 송출 (rqt 늦게 켜도 보이도록 방어)"""
        if self.last_snapshot is not None:
            try:
                img_msg = self.bridge.cv2_to_compressed_imgmsg(self.last_snapshot)
                self.annotated_pub.publish(img_msg)
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
