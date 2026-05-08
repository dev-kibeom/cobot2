from ..base_action import BaseAction

class PickHorizontal(BaseAction):
    action_name = 'pick_horizontal'

    def execute(self, target=None):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}' 수평 집기(pick_horizontal) 시작...")

        if not target: return False

        # ==========================================
        # 1. 1차 탐지 및 Search 연계
        # ==========================================
        coarse_pos = self.manager.get_vision_target(target)
        if not coarse_pos:
            logger.warn(f"⚠️ '{target}' 미발견. 주변 스캔을 시작합니다.")
            if not self.manager.perform('search', target=target): return False
            coarse_pos = self.manager.get_vision_target(target)
            if not coarse_pos: return False

        tx, ty, tz, rx, ry, rz = coarse_pos
        if not self.manager.perform('gripper_open'): return False

        # ==========================================
        # 2. Hover 및 2차 정밀 탐지 (손목 비틀기 전!)
        # ==========================================
        # 카메라가 물체를 정면으로 볼 수 있도록 타겟 상공(150mm)으로 이동
        approach_pos = [tx, ty, tz + 150.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return False
        
        self.wait(0.5) # 카메라 안정화
        
        logger.info("🎯 [2차 정밀 탐지] 영점 조정")
        fine_pos = self.manager.get_vision_target(target)
        
        if fine_pos:
            tx, ty, tz = fine_pos[0], fine_pos[1], fine_pos[2]
            logger.info("✨ 수평 집기 오차 보정 완료")

        # ==========================================
        # 3. 손목 비틀기 (MoveJ) 및 자세 업데이트
        # ==========================================
        # 이제 정밀 좌표(tx, ty, tz)를 얻었으니 손목을 꺾어줍니다.
        if ty >= 0:
            if not self.manager.perform('movej', joint=([0,0,0,70,0,0]), vel=100, acc=100, mode='rel'): return False
        else:
            if not self.manager.perform('movej', joint=([0,0,0,110,-180,0]), vel=100, acc=100, mode='rel'): return False
            
        # 비틀어진 손목의 각도를 현재 로봇 상태에서 읽어옴
        current_pos = self.get_current_posx()
        final_rx, final_ry, final_rz = current_pos[3], current_pos[4], current_pos[5]

        # ==========================================
        # 4. 수평 접근 및 그립
        # ==========================================
        # 비틀어진 각도를 유지하며 수직 하강
        grip_pos = [tx, ty, tz - 75.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False

        if not self.manager.perform('gripper_close'): return False

        # 안전 높이로 상승
        lift_pos = [tx, ty, tz + 150.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True