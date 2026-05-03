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
        
        print(f"'{target}' 픽업 위치로 이동합니다.")
        
        if not self.manager.perform('movel', pos=pos, mode='abs'): return False
        # if not self.manager.perform('movel', pos=[0, 0, -height, 0, 0, 0], mode='rel'): return False
        if not self.manager.perform('gripper_close'): return False
        if not self.manager.perform('movel', pos=[0, 0, -100, 0, 0, 0], mode='rel', ref='tool'): return False
        
        return True