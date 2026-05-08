from ..base_action import BaseAction

class PickVertical(BaseAction):
    action_name = 'pick'

    def execute(self, target=None):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}'수직 집기(pick) 시작...")
        
        if not target:
            logger.info("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        # ==========================================
        # 1차 탐지 및 Search 연계
        # ==========================================
        logger.info(f"🔍 [1차 탐지] '{target}' 위치 파악")
        coarse_pos = self.manager.get_vision_target(target)
        
        if not coarse_pos: 
            logger.warn(f"⚠️ '{target}' 미발견. 주변 스캔을 시작합니다.")
            if not self.manager.perform('search', target=target):
                return False  # 스캔 실패 시 동작 완전 종료
            
            # 스캔 성공 시 좌표 다시 획득!
            coarse_pos = self.manager.get_vision_target(target)
            if not coarse_pos: return False
        
        tx, ty, tz, rx, ry, rz = coarse_pos
        
        if not self.manager.perform('gripper_open'): return False

        # ==========================================
        # 2. Hover (상공 이동) 및 2차 정밀 탐지
        # ==========================================
        approach_pos = [tx, ty, tz + 100.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return False
        
        self.wait(0.5) # 카메라 흔들림 방지 및 안정화
        
        logger.info("🎯 [2차 정밀 탐지] 영점 조정")
        fine_pos = self.manager.get_vision_target(target)
        
        if fine_pos:
            dx = fine_pos[0] - coarse_pos[0]
            dy = fine_pos[1] - coarse_pos[1]
            logger.info(f"✨ 오차 보정 완료 (X: {dx:.1f}mm, Y: {dy:.1f}mm)")
            # 보정된 좌표로 덮어쓰기
            tx, ty, tz, rx, ry, rz = fine_pos
        else:
            logger.warn("⚠️ 2차 탐지 실패. 1차 좌표로 강행합니다.")
        
        # ==========================================
        # 3. 하강 및 그립
        # ==========================================
        grip_pos = [tx, ty, tz - 70.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False
        
        if not self.manager.perform('gripper_close'): return False
        
        lift_pos = [tx, ty, tz + 150.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True