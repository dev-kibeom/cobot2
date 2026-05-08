from ..base_action import BaseAction

class Pick(BaseAction):
    action_name = 'pick'

    def execute(self, target=None):
        pos = self.manager.get_vision_target(target)

        if not pos:
            if not self.manager.perform('finding', target=target):
                print(f"❌ '{target}' finding 실패")
                return False

            pos = self.manager.target_pos

            if not pos:
                print(f"❌ '{target}' finding 후에도 좌표가 없습니다.")
                return False

        
        tx, ty, tz, rx, ry, rz = pos
        print(f"🍎 '{target}' 좌표({tx:.1f}, {ty:.1f}, {tz:.1f})로 Pick 시퀀스를 시작합니다.")
        
        if not self.manager.perform('gripper_open'): return False

        # 어프로치: 사과 바로 위(100mm)로 안전하게 이동
        approach_pos = [tx, ty, tz + 100.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return False
        
        # 움켜쥐기 위해 하강: 표면 좌표보다 살짝 깊게 들어가서 꽉 쥠
        grip_pos = [tx, ty, tz - 70.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False
        
        # 잡기
        if not self.manager.perform('gripper_close'): return False
        
        # 들어 올리기: 다시 안전 높이로 상승
        lift_pos = [tx, ty, tz + 70.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True