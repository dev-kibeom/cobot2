from ..base_action import BaseAction

class Pick_horizontal(BaseAction):
    action_name = 'pick_horizontal'

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

        if tx > 500:
            # if not self.manager.perform('movej', joint=[0, 0, 20, 90, -90, 0], vel=100, acc=100, mode='rel'):
            if not self.manager.perform('movej', joint=[0, 0, 110, 90, 0, 0], vel=100, acc=100, mode='abs'):
                return False

        elif ty >= 0:
            if not self.manager.perform('movej', joint=[0, 0, 0, 110, -180, 0], vel=100, acc=100, mode='rel'):
                return False

        else:
            if not self.manager.perform('movej', joint=[0, 0, 0, 70, 0, 0], vel=100, acc=100, mode='rel'):
                return False

        current_pos = self.get_current_posx()

        rx = current_pos[3]
        ry = current_pos[4]
        rz = current_pos[5]
        # 어프로치: 사과 바로 위(50mm)로 안전하게 이동
        approach_pos = [tx, ty, tz + 50, rx, ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return False

        # 움켜쥐기 위해 하강: 표면 좌표보다 살짝 깊게 들어가서 꽉 쥠
        grip_pos = [tx, ty, tz - 30, rx, ry, rz]
        if not self.manager.perform('movel', pos=grip_pos, mode='abs'): return False

        # 잡기
        if not self.manager.perform('gripper_close'): return False

        # 들어 올리기: 다시 안전 높이로 상승
        lift_pos = [tx, ty, tz + 100, rx, ry, rz]
        if not self.manager.perform('movel', pos=lift_pos, mode='abs'): return False

        return True