from ..base_action import BaseAction

class ApproachAction(BaseAction):
    action_name = 'approach'

    def execute(self, target, **kwargs):
        logger = self.manager.node.get_logger()
        if not target or target == 'none':
            logger.error("🎯 타겟이 지정되지 않았습니다.")
            return False
            
        logger.info(f"🚁 '{target}'을(를) 향해 Coarse-to-Fine 정밀 접근을 시작합니다.")
        
        # 💡 팀장님이 vision_strategy.py에 구현하신 완벽한 2단 탐지 함수 호출!
        fine_pos = self.coarse_to_fine(target)
        
        if fine_pos:
            # 💡 [핵심] 2차 정밀 탐지 결과를 전역 매니저의 타겟 좌표에 덮어씌움!
            # 이후에 실행될 pick_horizontal 등의 동작은 오차가 사라진 이 좌표를 사용하게 됩니다.
            self.manager.target_pos = fine_pos
            logger.info("✅ 정밀 접근 및 2차 좌표 갱신 완료!")
            return True
        else:
            logger.error("❌ 정밀 접근 실패!")
            return False