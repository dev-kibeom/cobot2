from ..base_action import BaseAction

class Trash(BaseAction):
    action_name = 'trash'

    def execute(self):
        if not self.manager.perform('movej', 
                                    joint=[180,0,0,0,0,0], 
                                    mode='rel', 
                                    acc= 150, 
                                    vel=150): 
                                    return False
        if not self.manager.perform('gripper_open'): return False
        if not self.manager.perform('reset'): return False
        
        return True