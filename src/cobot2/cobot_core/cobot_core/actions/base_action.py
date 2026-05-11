from cobot_core.controller.dsr_controller import DSRobotController
from .vision_strategy import VisionStarategy

class BaseAction(DSRobotController, VisionStarategy):
    action_name = None 
    
    def __init__(self, manager):
        super().__init__(manager) # DSRRobotController에게 manager 넘겨줌
    
    @property
    def depth_offset(self):
        return self.manager.node.depth_offset
    
    @property
    def tilt_angle(self):
        return self.manager.node.tilt_angle
    

    def execute(self, **kwargs):
        raise NotImplementedError
    
    
    def reset(self):
        from DSR_ROBOT2 import movej
        from DSR_ROBOT2 import posj
        
        res = movej(posj(0, 0, 90, 0, 90, 0), vel=self.vel_angular, acc=self.acc_angular)
        
        if res != 0:
            print(f"⚠️ 예외사항 발생!: {res}")
            return False
        self.gripper_open()
        return True
    
    def clear_alarm(self):
        """공식 매뉴얼(SetRobotControl)에 기반한 하드웨어 에러/서보 복구 로직"""
        import DR_init
        from DSR_ROBOT2 import get_robot_state, drl_script_stop, DR_QSTOP_STO
        from dsr_msgs2.srv import SetRobotControl
        import time

        state_code = get_robot_state()
        print(f"🔄 현재 로봇 제어기 상태 코드: {state_code}")

        if state_code == 1:
            return True  # 이미 대기 중(정상)

        # 1. 안전을 위해 현재 실행 중인 스크립트 강제 정지
        try:
            drl_script_stop(DR_QSTOP_STO)
            time.sleep(1.0)
        except Exception as e:
            print(f"스크립트 정지 중 오류 (무시됨): {e}")

        # 2. 제어 상태 강제 변환 서비스 클라이언트 생성
        node = getattr(DR_init, '__dsr__node')
        ns = node.get_namespace()
        if ns == "/": ns = "/dsr01"  # 네임스페이스 기본값 처리
        
        cli = node.create_client(SetRobotControl, f'{ns}/system/set_robot_control')
        
        if not cli.wait_for_service(timeout_sec=2.0):
            print(f"⚠️ {ns}/system/set_robot_control 서비스를 찾을 수 없습니다.")
            return False

        req = SetRobotControl.Request()

        # 3. 상태 코드별 맞춤형 복구 명령 세팅
        if state_code == 5:
            print("🛠️ 보호 정지(Safe Stop) 감지됨. [리셋(2)] 명령을 전송합니다.")
            req.robot_control = 2
        elif state_code == 3:
            print("🔌 서보 꺼짐(Safe Off) 감지됨. [서보 ON(3)] 명령을 전송합니다.")
            req.robot_control = 3
        elif state_code == 6:
            print("🚨 비상 정지(E-Stop) 상태입니다! 물리적 버튼을 직접 해제해야 합니다.")
            return False
        else:
            print(f"⚠️ 기타 예외 상태({state_code}). 안전 리셋(2)을 시도합니다.")
            req.robot_control = 2

        # 4. 비동기 서비스 호출 (결과값 기다리지 않음)
        cli.call_async(req)
        
        # 5. 로봇의 실제 상태가 1(STANDBY)로 돌아올 때까지 직접 모니터링 (최대 10초)
        print("⏳ 복구 명령 전송됨. 로봇 하드웨어 안정화 대기 중...")
        start_time = time.time()
        
        while True:
            current_state = get_robot_state()
            
            if current_state == 1:
                print("🎉 로봇이 정상(STANDBY) 상태로 완벽히 복구되었습니다!")
                time.sleep(1.0) # 상태 1이 된 직후의 물리적 안정화를 위한 짧은 꿀잠
                return True
                
            if time.time() - start_time > 10.0:
                print(f"❌ 복구 시간 초과! (현재 상태 코드가 계속 {current_state}에 머물러 있습니다.)")
                return False
                
            time.sleep(0.5) # 0.5초마다 상태 재확인