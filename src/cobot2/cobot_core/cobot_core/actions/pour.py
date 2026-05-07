from ..base_action import BaseAction
import time

class Pour(BaseAction):
    """용기를 자연스럽게 기울여 내용물을 붓고 제자리로 돌아오는 동작"""
    action_name = 'pour'

    def execute(self):
        # if not self.manager.perform('amovej', pos=[0,-30,+30,0,0,0], vel=100, acc=100, time=0, mode='rel'): return False
        if not self.manager.perform('movej', joint=[0,0,0,-45,0,0], vel=100, acc=100, mode='rel'): return False



        return True