from ..base_action import BaseAction

class PickHorizontal(BaseAction):
    action_name = 'pick_horizontal'

    def execute(self, target=None):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}' 수평 집기(pick_horizontal) 시작...")

        if not target: return False

        fine_pos = self.coarse_to_fine(target, z_offset=300)
        tx, ty, tz, _, _, _ = fine_pos

        # ==========================================
        # 1. 손목 비틀기 (MoveJ) 및 자세 업데이트
        # ==========================================
        # 이제 정밀 좌표(tx, ty, tz)를 얻었으니 손목을 꺾어줍니다.
        if ty >= 0:
            if not self.manager.perform('movej', joint=([0,0,90,70,90,0]), vel=100, acc=100, mode='rel'): return False
        else:
            if not self.manager.perform('movej', joint=([0,0,90,70,90,0]), vel=100, acc=100, mode='abs'): return False
            
        # 비틀어진 손목의 각도를 현재 로봇 상태에서 읽어옴
        current_pos = self.get_current_posx()
        final_rx, final_ry, final_rz = current_pos[3], current_pos[4], current_pos[5]

        # ==========================================
        # 2. 수평 접근 및 그립
        # ==========================================
        
         # 안전 높이에서 증강
        lift_pos = [tx, ty, tz + 150.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False
        
        # 수직 하강
        grip_height = tz - self.d
        grip_pos = [tx, ty, tz - 75.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False

        if not self.manager.perform('gripper_close'): return False

        # 안전 높이로 상승
        lift_pos = [tx, ty, tz + 150.0, final_rx, final_ry, final_rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True