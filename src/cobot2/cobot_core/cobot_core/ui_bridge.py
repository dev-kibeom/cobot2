import rclpy
from rclpy.node import Node
import json
import time
from std_msgs.msg import String 

class UIBridgeNode(Node):
    def __init__(self):
        super().__init__('ui_bridge_node')
        
        # [설정 스위치]
        self.TEST_MODE = True 
        
        # 상태 log
        self.system_state = {
            "state": "IDLE",
            "current_action": "대기 중",
            "dsr_log": "",
            "stt_result": "",
            "voice_command": "",
            "detection": "NONE",
            "last_update": ""
        }

        self.get_logger().info(f"🌉 UI Bridge 가동 (테스트 모드: {self.TEST_MODE})")

        # 정보 통합 (Input)
        self.create_subscription(String, 'dsr_log', self.dsr_cb, 10)
        self.create_subscription(String, '/stt_result', self.stt_cb, 10)
        self.create_subscription(String, '/voice_command', self.cmd_cb, 10)
        self.create_subscription(String, '/status', self.status_cb, 10)
        self.create_subscription(String, '/detection', self.detection_cb, 10)

        # 개별 패스스루용 (팀원 테스트용)
        self.pub_stt_via = self.create_publisher(String, '/stt_result_via', 10)
        self.pub_cmd_via = self.create_publisher(String, '/voice_command_via', 10)
        
        # 통합 상태용 (최종 도커 파싱용)
        self.pub_ui_state = self.create_publisher(String, '/ui_bridge/state', 10)

        # 통합 전송 타이머 (10Hz)
        if not self.TEST_MODE:
            self.timer = self.create_timer(0.1, self.publish_combined_state)

    def dsr_cb(self, msg): self.system_state["dsr_log"] = msg.data
    
    def stt_cb(self, msg):
        self.system_state["stt_result"] = msg.data
        if self.TEST_MODE: # 테스트 중일 때만 즉시 전달
            self.pub_stt_via.publish(msg)

    def cmd_cb(self, msg):
        self.system_state["voice_command"] = msg.data
        if self.TEST_MODE:
            self.pub_cmd_via.publish(msg)

    def status_cb(self, msg):
        try:
            # state_manager나 executer가 보내는 JSON 파싱
            data = json.loads(msg.data)
            self.system_state["state"] = data.get("state", "UNKNOWN")
            self.system_state["current_action"] = data.get("current_action", "대기 중")
        except:
            self.system_state["state"] = msg.data

    def detection_cb(self, msg):
        self.system_state["detection"] = msg.data

    def publish_combined_state(self):
        self.system_state["last_update"] = time.strftime('%Y-%m-%d %H:%M:%S')
        msg = String()
        msg.data = json.dumps(self.system_state, ensure_ascii=False)
        self.pub_ui_state.publish(msg)

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