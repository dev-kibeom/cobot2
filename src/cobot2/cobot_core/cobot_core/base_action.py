# 최상단에 DSR_ROBOT2를 임포트하지 말 것

class BaseAction:
    action_name = None 

    GRIPPER_ON = 1
    GRIPPER_OFF = 0
    
    # 🚨 [안전 한계치 하드코딩] 협동로봇의 일반적인 안전 제한 속도
    LIMIT_VEL_LINEAR = 500.0   # 최대 직선 속도 (mm/s)
    LIMIT_ACC_LINEAR = 500.0   # 최대 직선 가속도 (mm/s^2)
    LIMIT_VEL_ANGULAR = 180.0  # 최대 관절 속도 (deg/s)
    LIMIT_ACC_ANGULAR = 180.0  # 최대 관절 가속도 (deg/s^2)
    
    def __init__(self, manager):
        self.manager = manager  # ActionManager 참조
    
    @property
    def vel_linear(self):
        current_val = self.manager.node.vel_linear
        return min(current_val, self.LIMIT_VEL_LINEAR)

    @property
    def acc_linear(self):
        current_val = self.manager.node.acc_linear
        return min(current_val, self.LIMIT_ACC_LINEAR)

    @property
    def vel_angular(self):
        current_val = self.manager.node.vel_angular
        return min(current_val, self.LIMIT_VEL_ANGULAR)

    @property
    def acc_angular(self):
        current_val = self.manager.node.acc_angular
        return min(current_val, self.LIMIT_ACC_ANGULAR)
    
    @property
    def tilt_angle(self):
        return self.manager.node.tilt_angle
    

    def execute(self, **kwargs):
        raise NotImplementedError
    
    def coarse_to_fine(self, target, z_offset=250.0):
        """2-Step Visual Servoing: 1차 탐지 -> 카메라 렌즈를 타겟 정상공에 정렬 -> 2차 정밀 탐지"""
        logger = self.manager.node.get_logger()
        
        # 1차 탐지
        logger.info(f"🔍 [1차 탐지] '{target}' 위치 파악")
        coarse_pos = self.manager.get_vision_target(target)
        
        if not coarse_pos:
            logger.warn(f"⚠️ 1차 탐지 결과:'{target}' 미발견. 주변 스캔을 시작합니다.")
            if not self.manager.perform('finding', target=target):
                return None
            coarse_pos = self.manager.target_pos
            if not coarse_pos: return None
            
        tx, ty, tz, rx, ry, rz = coarse_pos
        
        # =========================================================
        # 틸트 후 오프셋 수학적 역산
        # =========================================================
        # Y축(Pitch)을 파라미터에 설정된 각도만큼 기울입니다.
        tilt_ry = ry + self.tilt_angle
        
        dummy_base2gripper = self.manager.get_robot_pose_matrix(0, 0, 0, rx, tilt_ry, rz)
        cam_offset_matrix = dummy_base2gripper @ self.manager.T_gripper2cam
        
        offset_x = cam_offset_matrix[0, 3]
        offset_y = cam_offset_matrix[1, 3]
        offset_z = cam_offset_matrix[2, 3]
        
        cam_hover_x = tx - offset_x
        cam_hover_y = ty - offset_y
        cam_hover_z = (tz + z_offset) - offset_z

        # 타겟 상공(Hover)으로 이동
        logger.info(f"🚁 [Hovering] {self.tilt_angle}도 틸트 샷을 위해 카메라를 상공 {z_offset}mm에 정렬합니다.")
        approach_pos = [cam_hover_x, cam_hover_y, cam_hover_z, rx, tilt_ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return None
        
        self.wait(0.5) # 카메라 흔들림 안정화 대기
        
        # 2차 정밀 탐지
        logger.info("🎯 [2차 정밀 탐지] 영점 조정")
        fine_pos = self.manager.get_vision_target(target)
        
        if fine_pos:
            dx = fine_pos[0] - coarse_pos[0]
            dy = fine_pos[1] - coarse_pos[1]
            logger.info(f"✨ 오차 보정 완료 (X: {dx:.1f}mm, Y: {dy:.1f}mm)")
            
            # 수직으로 내려다볼 때 금속/반사 재질에 의해 Depth(Z)가 바닥을 뚫고 
            # 튀는 현상(IR 난반사)을 방지하기 위해, Z 높이는 가장 안전했던 1차 탐지 값을 유지합니다.
            if fine_pos[2] <= 30:
                fine_pos[2] = coarse_pos[2]
            
            return fine_pos
        else:
            logger.warn("⚠️ 2차 탐지 실패. 1차 좌표로 강행합니다.")
            return coarse_pos
    
    # ── 저수준 동작 래핑 (기본 기능) ──
    def movel(self, pos, vel=None, acc=None, time=0, radius=0, mode='abs', ref='base'):
        v = vel if vel is not None else self.vel_linear
        a = acc if acc is not None else self.acc_linear
        
        from DSR_ROBOT2 import movel
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL, DR_BASE, DR_TOOL
        from DSR_ROBOT2 import posx
        
        if mode == 'abs':
            mode = DR_MV_MOD_ABS
        elif mode == 'rel':
            mode = DR_MV_MOD_REL
        else:
            print("❌ 잘못된 move 모드!")
        
        if ref == 'base':
            ref = DR_BASE
        elif ref == 'tool':
            ref = DR_TOOL
        else:
            print("❌ 잘못된 move 모드!")
            return False
            
        pos = posx(pos)
        res = movel(pos, vel=v, acc=a, time=time, radius=radius, mod=mode, ref=ref)
        
        if res != 0:
            print(f"⚠️ 예외사항 발생!: {res}")
            return False
        
        return True

    def movej(self, joint, vel=None, acc=None, time=0, mode='rel'):
        v = vel if vel is not None else self.vel_angular
        a = acc if acc is not None else self.acc_angular
        
        from DSR_ROBOT2 import movej
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL
        from DSR_ROBOT2 import posj
        
        if mode == 'abs':
            mode = DR_MV_MOD_ABS
        elif mode == 'rel':
            mode = DR_MV_MOD_REL
        else:
            print("❌ 잘못된 move 모드!")
            
        joint = posj(joint)
        res = movej(joint, vel=v, acc=a, time=time, mod=mode)
        
        if res != 0:
            print(f"⚠️ 예외사항 발생!: {res}")
            return False
        
        return True

    def periodic(self, amp, period, repeat):
        from DSR_ROBOT2 import move_periodic, DR_BASE

        res = move_periodic(amp=amp, period=period, repeat=repeat, ref=DR_BASE)
        
        if res != 0:
            print(f"⚠️ 예외사항 발생!: {res}")
            return False
        
        return True
    
    def gripper_open(self):
        from DSR_ROBOT2 import set_digital_output
        
        set_digital_output(1, self.GRIPPER_OFF)
        set_digital_output(2, self.GRIPPER_ON)
        set_digital_output(3, self.GRIPPER_OFF)
        
        # 그리퍼의 예외상황에 대한 set_digital_output 반환값 처리도 필요
        self.wait(2)
    
    def gripper_open_little(self):
        from DSR_ROBOT2 import set_digital_output
        
        set_digital_output(1, self.GRIPPER_OFF)
        set_digital_output(2, self.GRIPPER_OFF)
        set_digital_output(3, self.GRIPPER_ON)
        
        # 그리퍼의 예외상황에 대한 set_digital_output 반환값 처리도 필요
        self.wait(2)
        
    def gripper_close(self):
        from DSR_ROBOT2 import set_digital_output
        
        set_digital_output(1, self.GRIPPER_ON)
        set_digital_output(2, self.GRIPPER_OFF)
        set_digital_output(3, self.GRIPPER_OFF)
        
        self.wait(2)

    def compliance_on(self, stx=[500, 500, 500, 100, 100, 100], ref='tool'):
        """
        순응 제어(Compliance Control)를 시작합니다.
        :param stx: 각 축(x, y, z, rx, ry, rz)에 대한 강성(Stiffness) 값의 리스트.
                    값이 작을수록 부드럽게(스프링처럼) 움직입니다.
        """
        from DSR_ROBOT2 import task_compliance_ctrl, set_ref_coord
        from DSR_ROBOT2 import DR_BASE, DR_TOOL
        
        # 순응 제어 활성화 '전'에만 기준 좌표계를 설정해야함
        ref_val = DR_TOOL if ref == 'tool' else DR_BASE
        set_ref_coord(ref_val)
            
        res = task_compliance_ctrl(stx=stx)
            
        self.wait(1)
        
        if res != 0:
            print(f"⚠️ 컴플라이언스 제어 활성화 실패: {res}")
            return False
            
        return True
    
    def compliance_off(self):
        """순응 제어를 해제하고 원래의 강성(Rigid) 제어 상태로 복귀합니다."""
        from DSR_ROBOT2 import release_compliance_ctrl, set_ref_coord, DR_BASE
        
        res = release_compliance_ctrl()
        set_ref_coord(DR_BASE)
        
        if res != 0:
            print(f"⚠️ 컴플라이언스 제어 해제 실패: {res}")
            return False
        
        return True
    
    def set_desired_force(self, fd=[0, 0, 0, 0, 0, 0], dir=[0, 0, 0, 0, 0, 0], ref='tool', mode='rel'):
        """
        로봇이 특정 방향으로 가할 목표 힘을 설정합니다.
        :param fd: 목표 힘/토크 리스트 (N 또는 Nm)
        :param dir: 힘을 가할 방향 (1: 활성화, 0: 비활성화)
        :param mode: 힘 제어 모드 ('abs' 또는 'rel')
        """
        from DSR_ROBOT2 import set_desired_force
        from DSR_ROBOT2 import DR_FC_MOD_ABS, DR_FC_MOD_REL
        
        fc_mode = DR_FC_MOD_ABS if mode == 'abs' else DR_FC_MOD_REL
        
        # DSR 파이썬 API에 ref 키워드가 없으므로 함수 호출 시 넘기지 않습니다.
        # (compliance_on에서 설정된 ref를 시스템이 자동으로 따라갑니다)
        res = set_desired_force(fd=fd, dir=dir, mod=fc_mode)
        
        if res != 0:
            print(f"⚠️ 목표 힘 설정 실패: {res}")
            return False
            
        return True
    
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
    
    def stop(self):
        try:
            # 구버전 API의 정지 함수인 task_stop을 마지막으로 시도해봅니다.
            from DSR_ROBOT2 import task_stop, STOP_TYPE_QUICK
            task_stop(STOP_TYPE_QUICK)
            print("🚨 [긴급] 로봇 모션을 강제 정지했습니다!")
        except ImportError:
            # 어떤 이름의 stop 함수도 없다면, 그냥 무시하고 넘어가서 파이썬 에러를 방지합니다.
            print("🚨 [긴급] 로봇 정지 명령 호출됨 (현재 API에서 지원하지 않아 로그만 출력합니다)")
            pass
        
    def wait(self, time=0):
        """wait(0)을 자주 쓰므로 편의를 위해 래핑"""
        from DSR_ROBOT2 import wait
        return wait(time)

    def get_current_posx(self):
        from DSR_ROBOT2 import get_current_posx

        pos, _ = get_current_posx()
        print(pos)
        return pos

    def get_current_posj(self):
        from DSR_ROBOT2 import get_current_posj

        joint, _ = get_current_posj()
        print(joint)
        return joint
    
# =======================================================================

    def amovej(self, joint, vel=None, acc=None, time=0, mode='rel'):        
        v = vel if vel is not None else self.vel_angular        
        a = acc if acc is not None else self.acc_angular
        
        from DSR_ROBOT2 import amovej        
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL        
        from DSR_ROBOT2 import posj
        
        if mode == 'abs':            
            mode = DR_MV_MOD_ABS        
        elif mode == 'rel':            
            mode = DR_MV_MOD_REL        
        else:            
            print("❌ 잘못된 move 모드!")            
            return False
        
        joint = posj(joint)
        
        res = amovej(
                    joint,
                    vel=v,
                    acc=a,
                    time=time,
                    mod=mode,
                    )
                    
        if res != 0:            
            print(f"⚠️ amovej 예외사항 발생!: {res}")            
            return False
        return True

# =======================================================================

    def amovel(self, pos, vel=None, acc=None, time=0, mode='abs', ref='base'):
        v = vel if vel is not None else self.vel_linear
        a = acc if acc is not None else self.acc_linear

        from DSR_ROBOT2 import amovel
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL, DR_BASE, DR_TOOL
        from DSR_ROBOT2 import posx

        if mode == 'abs':
            mode = DR_MV_MOD_ABS
        elif mode == 'rel':
            mode = DR_MV_MOD_REL
        else:
            print("❌ 잘못된 move 모드!")
            return False

        pos = posx(pos)

        res = amovel(
            pos,
            vel=v,
            acc=a,
            time=time,
            mod=mode,
        )

        if res != 0:
            print(f"⚠️ amovel 예외사항 발생!: {res}")
            return False

        return True

# =======================================================================

    def movesj(self, joints, vel=None, acc=None, time=0, mode='abs'):
        v = vel if vel is not None else self.vel_angular        
        a = acc if acc is not None else self.acc_angular
        
        from DSR_ROBOT2 import movesj        
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL        
        from DSR_ROBOT2 import posj

        if mode == 'abs':            
            mode = DR_MV_MOD_ABS        
        elif mode == 'rel':            
            mode = DR_MV_MOD_REL        
        else:            
            print("❌ 잘못된 move 모드!")            
            return False
            
        path = [posj(joint) for joint in joints]
        res = movesj(            
                    path,            
                    vel=v,            
                    acc=a,            
                    time=time,            
                    mod=mode,        
                    )
        if res != 0:            
            print(f"⚠️ movesj 예외사항 발생!: {res}")            
            return False
            
        return True

# =======================================================================

    def movesx(self, poses, vel=None, acc=None, time=0, 
								 mode='abs', ref='base'):        
        v = vel if vel is not None else self.vel_linear        
        a = acc if acc is not None else self.acc_linear
            
        from DSR_ROBOT2 import movesx        
        from DSR_ROBOT2 import DR_MV_MOD_ABS, DR_MV_MOD_REL, DR_BASE, DR_TOOL        
        from DSR_ROBOT2 import posx
        
        if mode == 'abs':
            mode = DR_MV_MOD_ABS
        elif mode == 'rel':
            mode = DR_MV_MOD_REL
        else:
            print("❌ 잘못된 move 모드!")
            return False
        
        if ref == 'base':
            ref = DR_BASE
        elif ref == 'tool':
            ref = DR_TOOL
        else:
            print("❌ 잘못된 ref 모드!")
            return False
        
        path = [posx(pos) for pos in poses]
        
        res = movesx(
                    path,
                    vel=v,
                    acc=a,
                    time=time,
                    mod=mode,
                    ref=ref,
                    )
                            
        if res != 0:
            print(f"⚠️ movesx 예외사항 발생!: {res}")
            return False

        return True