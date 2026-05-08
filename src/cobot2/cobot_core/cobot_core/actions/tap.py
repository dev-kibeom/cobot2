from ..base_action import BaseAction

class Push(BaseAction):
    action_name = 'push'

    def execute(self,target=None):

        if not target:
            print("❌ 타겟이 지정되지 않았습니다.")
            return False
        
        pos = self.manager.get_vision_target(target)
        
        if not pos:
            self.manager.perform('finding', target=target)
            return False

        tx, ty, tz, rx, ry, rz = pos

        if not self.manager.perform('movel', pos=[tx, ty, tz+100, rx, ry, rz], vel=100, acc=100, mode='abs'): return False
        if not self.manager.perform('periodic', amp=[0, 0, 5, 0, 0, 0], period=[0, 0, 0.5, 0, 0, 0], repeat=2): return False
        return True