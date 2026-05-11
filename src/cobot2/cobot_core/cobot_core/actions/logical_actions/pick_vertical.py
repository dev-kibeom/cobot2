from ..base_action import BaseAction

class PickVertical(BaseAction):
    action_name = 'pick_vertical'

    def execute(self, target=None):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}'수직 집기(pick) 시작...")
        
        if not target:
            logger.info("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        fine_pos = self.coarse_to_fine(target, z_offset=300)
        tx, ty, tz, rx, ry, rz = fine_pos
        
        # 동적 안전 한계선 적용
        dynamic_limit = self.get_dynamic_min_depth(ry)
        grip_pos_z = tz + self.depth_offset
        
        if grip_pos_z < dynamic_limit:
            logger.warn(f"⚠️ 바닥 충돌 위험! 수직 파지 고도를 {grip_pos_z:.1f}에서 {dynamic_limit:.1f}로 보정합니다.")
            grip_pos_z = dynamic_limit
            
        # ==========================================
        # 3. 하강 및 그립
        # ==========================================
        grip_pos = [tx, ty, grip_pos_z, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False
        
        if not self.manager.perform('gripper_close'): return False
        
        lift_pos = [tx, ty, tz + 150.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False
        
        # 붓기를 위한 임시
        if not self.manager.perform('movej', joint=[0,0,90,0,90,0], acc=100, vel=100, mode='abs'): return False

        return True