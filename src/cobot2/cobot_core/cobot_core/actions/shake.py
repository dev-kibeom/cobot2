from ..base_action import BaseAction

class Shake(BaseAction):
    action_name = 'shake'

    def execute(self, amp=[0, 0, 40, 0, 0, 0], period=[0, 0, 0.5, 0, 0, 0], repeat=5):
        """반복운동 실행시 좌표계에대한 진폭값(amp=list[6]), 주기(period=list[6]), 반복회수(repeat=int)"""
        
        # 이미 잡고있는 상태라 가정
        # if not self.manager.perform('gripper_close'): return False
        # 홈 위치 이동 후 'shake'
        if not self.manager.perform('movesj', joints=[[0, 0, 90,0, 90, 0]], vel = 100, acc = 100, mode = 'abs'): return False
        if not self.manager.perform('amovej', joint=([0,0,0,80,0,0]),vel=50, acc=50, mode='rel'): return False
        if not self.manager.perform('movej', joint=([0,0,0,0,0,180])): return False
        if not self.manager.perform('periodic', amp=amp, period=period, repeat=repeat): return False
        if not self.manager.perform('amovej', joint=([0,0,0,0,0,-180])): return False
        if not self.manager.perform('movej', joint=([0,0,0,-80,0,0]),vel=50, acc=50, mode='rel'): return False
        
        return True