from ..base_action import BaseAction
import time

class Pour(BaseAction):
    """용기를 자연스럽게 기울여 내용물을 붓고 제자리로 돌아오는 동작"""
    action_name = 'pour'

    def execute(self):
        pos = self.manager.get_vision_target(target)

        if not pos:
            if not self.manager.perform('finding', target=target):
                print(f"❌ '{target}' finding 실패")
                return False

            pos = self.manager.target_pos

            if not pos:
                print(f"❌ '{target}' finding 후에도 좌표가 없습니다.")
                return False
                
        # 붓는 위치로 이동
        if not self.manager.perform('movel', pos=pos,vel=100,acc=100): return False
        
        pos = self.get_current_posx()
        if not self.manager.perform('amovel', pos=[pos[0],pos[1],pos[2]-100,pos[3],pos[4],pos[5]], 
        vel=100, acc=100, mode='abs', ref='base'): return False
        if not self.manager.perform('movej', joint=[0,0,0,-45,0,0], vel=100, acc=100, mode='rel'): return False
        
        # 부을 때 까지 대기
        if not self.manager.perform('wait', time=3): return False
        
        # # pos = self.get_current_posx()
        # if not self.manager.perform('movel', pos=[0,50,0,0,0,0],
        # vel=100, acc=100, mode='rel', ref='base'): return False
        
        return True