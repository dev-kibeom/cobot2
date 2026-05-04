from ..base_action import BaseAction

class Pick(BaseAction):
    action_name = 'pick'

    def execute(self, target=None):
        if not target:
            print("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        # 👁️ 비전 탐색: "타겟"의 픽업용 3D 좌표 (기존 height의 오프셋 설정은 action_manager의 DEPTH_OFFSET 참고)
        pos = self.manager.get_vision_target(target)
        if not pos: 
            return False
        
        tx, ty, tz, rx, ry, rz = pos
        print(f"🍎 '{target}' 좌표({tx:.1f}, {ty:.1f}, {tz:.1f})로 Pick 시퀀스를 시작합니다.")
        
        if not self.manager.perform('gripper_open'): return False

        # 어프로치: 사과 바로 위(100mm)로 안전하게 이동
        approach_pos = [tx, ty, tz + 100.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return False
        
        # 움켜쥐기 위해 하강: 표면 좌표보다 살짝 깊게 들어가서 꽉 쥠
        grip_pos = [tx, ty, tz - 50.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False
        
        # 잡기
        if not self.manager.perform('gripper_close'): return False
        
        # 들어 올리기: 다시 안전 높이로 상승
        lift_pos = [tx, ty, tz + 150.0, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True