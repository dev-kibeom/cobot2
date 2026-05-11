import rclpy
import time
import json
from rclpy.node import Node
from std_msgs.msg import String
from dsr_msgs2.srv import SetRobotControl

class StateManager(Node):
    def __init__(self):
        super().__init__('state_manager')
        
        self.last_heartbeat = time.time()
        self.is_locked = False  # 🚨 E-Stop 발동 시 시스템을 잠그는 플래그

        self.create_timer(1.0, self.watchdog_check)
        
        # UI Bridge 모드와 상관없이 항상 발행되는 /status를 생존 신호로 사용합니다.
        self.create_subscription(String, '/status', self.hb_cb, 10)
        
        # 👨‍💻 관리자 UI 명령 구독 (수동 E-Stop / Unlock)
        self.create_subscription(String, '/admin_command', self.admin_cmd_cb, 10)

        # 하드웨어 제어 명령
        self.estop_cli = self.create_client(SetRobotControl, '/dsr01/system/set_robot_control')

        self.get_logger().info("🛡️ Watchdog & Admin Control Ready: 자동 감시 및 관리자 명령 대기 중")

    def hb_cb(self, msg):
        """정상 상태일 때 심박수 갱신"""
        if not self.is_locked:
            self.last_heartbeat = time.time()

    def watchdog_check(self):
        """통신 두절 시 자동 E-Stop 발동"""
        if self.is_locked:
            return  # 이미 잠겨있다면 중복 체크 안 함
            
        if (time.time() - self.last_heartbeat) > 5.0:
            self.get_logger().fatal("💀 시스템 응답 없음! [자동] 비상 정지 발동!")
            self.trigger_estop()

    # ==========================================
    # 👨‍💻 관리자 UI 명령 처리 로직
    # ==========================================
    def admin_cmd_cb(self, msg):
        """관리자 UI에서 보낸 명령(JSON) 처리"""
        try:
            data = json.loads(msg.data)
            cmd = data.get("command", "").upper()
            
            if cmd == "ESTOP":
                self.get_logger().fatal("🛑 [ADMIN] 관리자 수동 비상 정지(E-STOP) 요청 접수!")
                self.trigger_estop()
                
            elif cmd == "UNLOCK":
                self.get_logger().info("🔓 [ADMIN] 관리자 시스템 잠금 해제(UNLOCK) 요청 접수!")
                self.trigger_unlock()
                
        except Exception as e:
            self.get_logger().warn(f"관리자 명령 파싱 실패: {e}")

    # ==========================================
    # 🤖 하드웨어 제어 로직
    # ==========================================
    def trigger_estop(self):
        """로봇 강제 정지 및 시스템 잠금"""
        self.is_locked = True
        
        if self.estop_cli.wait_for_service(timeout_sec=1.0):
            req = SetRobotControl.Request()
            req.robot_control = 2 # 로봇 제어 권한 탈취 후 강제 보호 정지(Safe Stop)
            self.estop_cli.call_async(req)
            self.get_logger().error("🛑 로봇 하드웨어 보호 정지 명령 전송 완료. (시스템 잠금 상태)")
        else:
            self.get_logger().error("⚠️ 비상 정지 서비스를 찾을 수 없습니다!")

    def trigger_unlock(self):
        """로봇 알람 해제, 서보 온 및 시스템 잠금 해제"""
        if self.estop_cli.wait_for_service(timeout_sec=1.0):
            # 1. 에러 알람 초기화 (Reset)
            req_reset = SetRobotControl.Request()
            req_reset.robot_control = 2 # 이전 base_action.py의 clear_alarm 로직과 동일
            self.estop_cli.call_async(req_reset)
            self.get_logger().info("⏳ 1/2: 로봇 알람 리셋 명령 전송")
            
            time.sleep(0.5) # 하드웨어 반영 대기
            
            # 2. 서보 모터 다시 켜기 (Servo ON)
            req_servo = SetRobotControl.Request()
            req_servo.robot_control = 3 
            self.estop_cli.call_async(req_servo)
            self.get_logger().info("⏳ 2/2: 로봇 서보 ON 명령 전송")
            
            # 3. 내부 시스템 잠금 해제
            self.is_locked = False
            self.last_heartbeat = time.time() # 심박수 초기화
            self.get_logger().info("✅ 시스템 잠금 해제 완료! 정상 작동을 재개할 수 있습니다.")
        else:
            self.get_logger().error("⚠️ 제어 서비스를 찾을 수 없어 Unlock에 실패했습니다.")

def main(args=None):
    rclpy.init(args=args)
    node = StateManager()
    try: rclpy.spin(node)
    except: pass
    finally: rclpy.shutdown()