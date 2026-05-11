import rclpy
from rclpy.node import Node
import json

from std_msgs.msg import String 
# 예: from od_msg.msg import DetectionResult

class UIBridgeNode(Node):
    def __init__(self):
        super().__init__('ui_bridge_node')
        
        # 📦 UI로 보낼 통합 데이터 저장소 (딕셔너리)
        self.system_state = {
            "dsr_log": "",
            "stt_result": "",
            "voice_command": "",
            "status": "IDLE",
            "detection": ""
        }

        self.get_logger().info("🌉 UI Bridge Node 시작: 데이터 통합 중...")

        # 1. 흩어진 5개의 토픽을 모두 구독 (Subscribers)
        self.sub_dsr = self.create_subscription(String, 'dsr_log', self.dsr_cb, 10)
        self.sub_stt = self.create_subscription(String, '/stt_result', self.stt_cb, 10)
        self.sub_cmd = self.create_subscription(String, '/voice_command', self.cmd_cb, 10)
        self.sub_status = self.create_subscription(String, '/status', self.status_cb, 10)
        self.sub_det = self.create_subscription(String, '/detection', self.detection_cb, 10)
        
        self.pub_stt_via = self.create_publisher(String, '/stt_result_via', self.stt_cb, 10)
        self.pub_cmd_via = self.create_publisher(String, '/voice_command_via', self.cmd_cb, 10)

        # 2. 통합된 상태를 UI나 DB로 한 번에 쏴줄 퍼블리셔
        # UI 쪽 웹소켓 노드나 클라이언트가 이 토픽 하나만 구독하면 됩니다!
        # self.pub_ui_state = self.create_publisher(String, '/ui_bridge/state', 10)

        # 3. 0.1초(10Hz)마다 현재 상태를 모아서 전송 (원하는 속도로 조절 가능)
        # self.timer = self.create_timer(0.1, self.publish_state)

    # --- 콜백 함수들 (데이터가 들어올 때마다 최신 값으로 갱신) ---
    def dsr_cb(self, msg):
        self.system_state["dsr_log"] = msg.data

    def stt_cb(self, msg):
        self.system_state["stt_result"] = msg.data
        self.pub_stt_via.publish(msg.data)

    def cmd_cb(self, msg):
        self.system_state["voice_command"] = msg.data
        self.pub_cmd_via.publish(msg.data)

    def status_cb(self, msg):
        self.system_state["status"] = msg.data

    def detection_cb(self, msg):
        self.system_state["detection"] = msg.data # 커스텀 메시지면 msg.class_name 등으로 접근

    # --- 퍼블리시 함수 ---
    def publish_state(self):
        msg = String()
        # 딕셔너리를 예쁜 JSON 문자열로 변환 (한글 깨짐 방지: ensure_ascii=False)
        msg.data = json.dumps(self.system_state, ensure_ascii=False)
        
        self.pub_ui_state.publish(msg)
        
        # 💡 만약 로컬 DB(MySQL 등)에 데이터를 넣고 싶다면 이 부분에 DB Insert 로직을 한 줄 추가하시면 됩니다.

def main(args=None):
    rclpy.init(args=args)
    node = UIBridgeNode()
    
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()