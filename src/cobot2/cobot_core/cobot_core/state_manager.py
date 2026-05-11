import rclpy
import json
from rclpy.node import Node
from std_msgs.msg import String
from dsr_msgs2.srv import SetRobotControl

class StateManager(Node):
    def __init__(self):
        super().__init__('state_manager')
        
        # 👨‍💻 관리자 UI 명령 구독 (수동 E-Stop / Unlock 전용)
        self.create_subscription(String, '/admin_command', self.admin_cmd_cb, 10)
        
        # 하드웨어 제어 서비스 클라이언트
        self.estop_cli = self.create_client(SetRobotControl, '/dsr01/system/set_robot_control')
        
        self.get_logger().info("🛡️ State Manager Ready: 자동 비상정지 해제됨. 관리자 수동 개입만 대기합니다.")

    def admin_cmd_cb(self, msg):
        """관리자 UI에서 보낸 명령(JSON) 처리"""
        try:
            data = json.loads(msg.data)
            cmd = data.get("command", "").upper()
            
            if cmd == "ESTOP":
                self.get_logger().fatal("🛑 [ADMIN] 수동 비상 정지(E-STOP) 요청 접수!")
                self.trigger_estop()
                
            elif cmd == "UNLOCK":
                self.get_logger().info("🔓 [ADMIN] 시스템 잠금 해제(UNLOCK) 요청 접수!")
                self.trigger_unlock()
                
        except Exception as e:
            self.get_logger().warn(f"관리자 명령 파싱 실패: {e}")

    def trigger_estop(self):
        """로봇 하드웨어 강제 보호 정지"""
        if self.estop_cli.wait_for_service(timeout_sec=1.0):
            req = SetRobotControl.Request()
            req.robot_control = 2 # 로봇 제어 권한 탈취 후 Safe Stop
            self.estop_cli.call_async(req)
        else:
            self.get_logger().error("⚠️ 비상 정지 서비스를 찾을 수 없습니다!")

    def trigger_unlock(self):
        """로봇 알람 해제 및 서보 온"""
        if self.estop_cli.wait_for_service(timeout_sec=1.0):
            import time
            req_reset = SetRobotControl.Request()
            req_reset.robot_control = 2 
            self.estop_cli.call_async(req_reset)
            self.get_logger().info("⏳ 1/2: 로봇 알람 리셋")
            
            time.sleep(0.5) 
            
            req_servo = SetRobotControl.Request()
            req_servo.robot_control = 3 
            self.estop_cli.call_async(req_servo)
            self.get_logger().info("✅ 2/2: 서보 ON 및 잠금 해제 완료")
        else:
            self.get_logger().error("⚠️ 제어 서비스를 찾을 수 없습니다.")

def main(args=None):
    rclpy.init(args=args)
    node = StateManager()
    try: rclpy.spin(node)
    except: pass
    finally: rclpy.shutdown()

if __name__ == '__main__':
    main()