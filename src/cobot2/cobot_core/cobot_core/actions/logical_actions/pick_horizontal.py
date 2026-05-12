from ..base_action import BaseAction

class PickHorizontal(BaseAction):
    action_name = 'pick_horizontal'

    def execute(self, target=None, **kwargs):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}' 수평 집기(pick_horizontal) 시작...")

        if not target: return False

        # ==========================================
        # 💡 [핵심 수정] BT가 찾아둔 좌표가 있는지 먼저 확인!
        # ==========================================
        if self.manager.target_pos is not None:
            logger.info("✅ BT(finding)에서 탐지한 좌표를 그대로 사용합니다.")
            fine_pos = self.manager.target_pos
            
            # 🚨 1회용으로 썼으니 다음 동작을 위해 기억을 지워줍니다 (안전장치)
            self.manager.target_pos = None 
        else:
            logger.warn("⚠️ 저장된 좌표가 없어 객체 탐지를 재시도합니다 (coarse_to_fine).")
            fine_pos = self.coarse_to_fine(target, z_offset=300)
            if not fine_pos: return False
            
        tx, ty, tz, _, _, _ = fine_pos
        
        self.gripper_open()
        
        # ==========================================
        # 3. 손목 비틀기 (MoveJ) 및 자세 업데이트
        # ==========================================
        # 이제 정밀 좌표(tx, ty, tz)를 얻었으니 손목을 꺾어줍니다.
        if ty >= 0:
            if not self.manager.perform('movej', joint=([0,0,90,70,90,0]), vel=100, acc=100, mode='abs'): return False
        else:
            if not self.manager.perform('movej', joint=([0,0,0,110,-180,0]), vel=100, acc=100, mode='abs'): return False
            
        # 비틀어진 손목의 각도를 현재 로봇 상태에서 읽어옴
        current_pos = self.get_current_posx()
        final_rx, final_ry, final_rz = current_pos[3], current_pos[4], current_pos[5]

        # ==========================================
        # 4. 수평 접근 및 그립
        # ==========================================
        
         # 안전 높이에서 증강
        lift_pos = [tx, ty, tz + 150.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False
        
        # 동적 안전 한계선 적용
        dynamic_limit = self.get_dynamic_min_depth(final_ry)
        grip_pos_z = tz + self.depth_offset
        
        if grip_pos_z < dynamic_limit:
            logger.warn(f"⚠️ 바닥 충돌 위험! 수직 파지 고도를 {grip_pos_z:.1f}에서 {dynamic_limit:.1f}로 보정합니다.")
            grip_pos_z = dynamic_limit
            
        # 수직 하강
        grip_pos = [tx, ty, grip_pos_z, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False

        if not self.manager.perform('gripper_close'): return False

        # 안전 높이로 상승
        lift_pos = [tx, ty, tz + 150.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True