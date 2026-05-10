from ..base_action import BaseAction

class PickVertical(BaseAction):
    action_name = 'pick'

    def execute(self, target=None):
        logger = self.manager.node.get_logger()
        logger.info(f"🔎 '{target}'수직 집기(pick) 시작...")
        
        if not target:
            logger.info("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        fine_pos = self.coarse_to_fine(target, z_offset=200)
        tx, ty, tz, rx, ry, rz = fine_pos
        
        # ==========================================
        # 3. 하강 및 그립
        # ==========================================
        grip_pos = [tx, ty, tz - 70.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False
        
        if not self.manager.perform('gripper_close'): return False
        
        lift_pos = [tx, ty, tz + 150.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True