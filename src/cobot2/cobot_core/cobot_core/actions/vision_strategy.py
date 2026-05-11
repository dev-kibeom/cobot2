import math

class VisionStarategy:
    
    def coarse_to_fine(self, target, z_offset=250.0):
        """2-Step Visual Servoing: 1차 탐지 -> 카메라 렌즈를 타겟 정상공에 정렬 -> 2차 정밀 탐지"""
        logger = self.manager.node.get_logger()
        
        # 1차 탐지
        logger.info(f"🔍 [1차 탐지] '{target}' 위치 파악")
        coarse_pos = self.manager.get_vision_target(target)
        
        if not coarse_pos:
            logger.warn(f"⚠️ 1차 탐지 결과:'{target}' 미발견. 주변 스캔을 시작합니다.")
            if not self.manager.perform('finding', target=target):
                return None
            coarse_pos = self.manager.target_pos
            if not coarse_pos: return None
            
        tx, ty, tz, rx, ry, rz = coarse_pos
        
        # =========================================================
        # 틸트 후 오프셋 수학적 역산
        # =========================================================
        # Y축(Pitch)을 파라미터에 설정된 각도만큼 기울입니다.
        tilt_ry = ry + self.tilt_angle
        
        dummy_base2gripper = self.manager.get_robot_pose_matrix(0, 0, 0, rx, tilt_ry, rz)
        cam_offset_matrix = dummy_base2gripper @ self.manager.T_gripper2cam
        
        offset_x = cam_offset_matrix[0, 3]
        offset_y = cam_offset_matrix[1, 3]
        offset_z = cam_offset_matrix[2, 3]
        
        cam_hover_x = tx - offset_x
        cam_hover_y = ty - offset_y
        cam_hover_z = (tz + z_offset) - offset_z

        # 타겟 상공(Hover)으로 이동
        logger.info(f"🚁 [Hovering] {self.tilt_angle}도 틸트 샷을 위해 카메라를 상공 {z_offset}mm에 정렬합니다.")
        approach_pos = [cam_hover_x, cam_hover_y, cam_hover_z, rx, tilt_ry, rz]
        if not self.manager.perform('movel', pos=approach_pos, mode='abs'): return None
        
        self.wait(0.5) # 카메라 흔들림 안정화 대기
        
        # 2차 정밀 탐지
        logger.info("🎯 [2차 정밀 탐지] 영점 조정")
        fine_pos = self.manager.get_vision_target(target)
        
        if fine_pos:
            dx = fine_pos[0] - coarse_pos[0]
            dy = fine_pos[1] - coarse_pos[1]
            logger.info(f"✨ 오차 보정 완료 (X: {dx:.1f}mm, Y: {dy:.1f}mm)")
            
            # 수직으로 내려다볼 때 금속/반사 재질에 의해 Depth(Z)가 바닥을 뚫고 
            # 튀는 현상(IR 난반사)을 방지하기 위해, Z 높이는 가장 안전했던 1차 탐지 값을 유지합니다.
            if fine_pos[2] <= 30:
                fine_pos[2] = coarse_pos[2]
            
            return fine_pos
        else:
            logger.warn("⚠️ 2차 탐지 실패. 1차 좌표로 강행합니다.")
            return coarse_pos
    
    def get_dynamic_min_depth(self, target_ry):
        """
        목표 Pitch 각도(ry)를 기반으로 바닥과 충돌하지 않는 최소 안전 고도(Z)를 계산합니다.
        """
        # 두산 로봇 기준 ry=180이 수직 하강(바닥과 90도), ry=90이 수평(바닥과 0도)
        angle_to_floor = abs(target_ry - 90.0) 
        
        # 파라미터 서버에서 값 가져오기
        L = getattr(self.manager.node, 'gripper_length', 150.0)
        base_safety = self.manager.node.min_depth # 예: 30mm (테이블 마진)
        
        # 그리퍼 길이 * sin(바닥과의 각도)
        dynamic_margin = L * math.sin(math.radians(angle_to_floor))
        
        safe_z = base_safety + dynamic_margin
        self.manager.node.get_logger().info(
            f"🛡️ 동적 충돌 한계선: Z={safe_z:.1f}mm (마진:{dynamic_margin:.1f}mm, 각도:{angle_to_floor:.1f}도)"
        )
        return safe_z