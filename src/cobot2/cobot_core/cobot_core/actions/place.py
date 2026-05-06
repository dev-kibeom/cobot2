from ..base_action import BaseAction

class Place(BaseAction):
    action_name = 'place'

    def execute(self, target=None):
        if not target:
            print("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        # 👁️ 비전 탐색: "타겟"의 픽업용 3D 좌표
        pos = self.manager.get_vision_target(target)
        if not pos: 
            return False
        
        print(f"'{target}' 근처로 이동하여 물체를 내려놓습니다.")
        
        if not self.manager.perform('movel', pos=pos, mode='abs'): return False
        # if not self.manager.perform('movel', pos=[0,0,-height,0,0,0], mode='rel'): return False
        if not self.manager.perform('gripper_open'): return False
        if not self.manager.perform('movel', pos=[0,0,-100,0,0,0], mode='rel', ref='tool'): return False
        
        return True