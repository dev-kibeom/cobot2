import os
import math
import numpy as np
import rclpy
import importlib
import pkgutil
import cobot_core.actions as actions

from ament_index_python.packages import get_package_share_directory
from .base_action import BaseAction
from od_msg.srv import GetTargetPose
        
class ActionManager():
    def __init__(self, node):
        self.node = node
        self._action_map = {}
        self.is_error = False   # 시스템 에러 상태 플래그
        
        self.target = None
        self.target_pos = None
        
        # 👁️ 비전 서비스 클라이언트 초기화 (공용 인터페이스)
        self.vision_client = self.node.create_client(GetTargetPose, '/get_3d_position')
        
        # Hand-Eye 캘리브레이션 행렬 로드
        package_path = get_package_share_directory("cobot_core")
        matrix_path = os.path.join(package_path, "resource", "T_gripper2camera.npy")
        
        try:
            self.T_gripper2cam = np.load(matrix_path)
            self.node.get_logger().info("✅ Hand-Eye 캘리브레이션 매트릭스 로드 완료.")
        except Exception as e:
            self.node.get_logger().error(f"❌ 매트릭스 로드 실패: {e}")
            self.T_gripper2cam = np.eye(4)
            
        self._register_methods()
        self._register_custom_actions()
    
    
    def perform(self, action_name, **kwargs):
        if self.is_error:
            self.node.get_logger().info("에러 상황으로 perform 중단")
            return False
        
        action = self._action_map.get(action_name)
        if not action:
            self.node.get_logger().info(f"Error: {action_name}을 찾을 수 없습니다.")
            return False

        # callable(action.execute)를 통해 실행 가능 여부만 체크
        execute_func = getattr(action, 'execute', None)
        if callable(execute_func):
            # 파이썬 코드 에러 발생 시에도 안전망이 작동하도록 try-except
            try:
                result = execute_func(**kwargs)
            except Exception as e:
                self.node.get_logger().error(f"🐍 [PYTHON ERROR] {action_name} 파라미터 또는 문법 오류: {e}")
                self.handle_critical_error(action_name) # 에러 시에도 무조건 compliance_off 실행!
                return False
            
            # 동작 실패(False 반환) 감지 시 처리
            if result is False:
                self.handle_critical_error(action_name)
                return False
            
            return True
            
        return False
    
    def _register_methods(self):
        """BaseAction의 메서드 등록 (movel, movej, gripper_open 등)"""
        
        # 메서드 가져오기용 인스턴스 생성
        base = BaseAction(self)
        methods = ['movel', 'movej', 'wait', 'reset', 
                   'gripper_open', 'gripper_close', 'gripper_open_little',
                   'compliance_on', 'compliance_off', 'set_desired_force',
                   'periodic','amovej','amovel', 'movesx', 'movesj',
                   'get_current_posx','get_current_posj',
                   'clear_alarm', 'stop']
        
        for m in methods:
            # getattr(obj, name): 객체에서 속성 가져오기
            method = getattr(base, m)
            self._action_map[m] = type(f"Method_{m}", (object,), {"execute": staticmethod(method)})
            self.node.get_logger().info(f"Method Registered: {m}")
            
    def _register_custom_actions(self):
        """actions 폴더 내의 모든 액션들을 자동으로 등록"""
        # 파일 임포트
        for _, name, _ in pkgutil.iter_modules(actions.__path__):
            full_module_name = f"cobot_core.actions.{name}"
            importlib.import_module(full_module_name)
        
        # 액션 등록
        for cls in BaseAction.__subclasses__():
            action_name = cls.action_name or cls.__name__.lower()
            
            # 동작 이름에 맞는 인스턴스를 등록
            self._action_map[action_name] = cls(self)
            self.node.get_logger().info(f"Action Registered: {action_name}")

    def get_robot_pose_matrix(self, x, y, z, a, b, c):
        """Doosan API 기준인 Z-Y-Z 오일러 각도 회전 행렬 적용"""
        a, b, c = math.radians(a), math.radians(b), math.radians(c)

        # Z-Y-Z 회전 행렬
        Rz1 = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
        Ry  = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
        Rz2 = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])

        R = Rz1 @ Ry @ Rz2
        T = np.eye(4)
        T[:3, :3] = R
        T[0, 3], T[1, 3], T[2, 3] = x, y, z
        return T
    
    def transform_to_base(self, camera_coords):
        """카메라 좌표계를 로봇 Base 좌표계(순수 절대 좌표)로 변환"""
        try:
            from DSR_ROBOT2 import get_current_posx, DR_BASE
            robot_posx = get_current_posx(DR_BASE)[0]  # 현재 로봇의 [x, y, z, rx, ry, rz]
        except Exception as e:
            self.node.get_logger().error("로봇 좌표 획득 실패 (시뮬레이션 모드일 수 있음)")
            return None

        coord = np.append(np.array(camera_coords), 1)  # [x, y, z, 1]
        x, y, z, rx, ry, rz = robot_posx

        base2gripper = self.get_robot_pose_matrix(x, y, z, rx, ry, rz)
        base2cam = base2gripper @ self.T_gripper2cam

        # 1. Base 좌표로 변환
        target_base_coord = np.dot(base2cam, coord)[:3]
        
        # 2. 바닥 충돌 방지 최소 높이(Z) 보정
        target_base_coord[2] = max(target_base_coord[2], self.node.min_depth)

        # 3. 6자유도 리스트로 반환 (손목 각도는 현재 상태 유지)
        result_pos = target_base_coord.tolist()
        result_pos.extend([rx, ry, rz])

        return result_pos
        
    def get_vision_target(self, target_name):
        """ Action 모듈이 타겟의 최신 3D 좌표를 원할 때 호출"""
        if not self.vision_client.wait_for_service(timeout_sec=2.0):
            self.node.get_logger().error("👁️ ❌ Vision AI 노드(/get_3d_position)가 응답하지 않습니다.")
            return None
        
        self.target = target_name
        
        # 서비스 요청 객체 생성
        req = GetTargetPose.Request()
        req.target_name = target_name
        self.node.get_logger().info(f"👁️ 🔍 '{target_name}'의 현재 좌표를 Vision AI에 요청합니다...")
        
        # 서비스 호출
        future = self.vision_client.call_async(req)
        rclpy.spin_until_future_complete(self.node, future)
        response = future.result()
        
        # 결과 검증 및 반환
        if response is not None and response.success:
            cam_coord = list(response.position)
            base_coord = self.transform_to_base(cam_coord)
            
            if base_coord:
                self.node.get_logger().info(f"👁️ ✅ '{target_name}' 최종 변환 좌표: {base_coord}")
                
                self.target_pos = base_coord
                
                return base_coord
            return None
        else:
            err_msg = response.message if response else "Service call failed"
            self.node.get_logger().error(f"👁️ ❌ '{target_name}' 탐지 실패: {err_msg}")
            return None
    
    def handle_critical_error(self, action_name):
        """어떤 동작이든 실패하면 즉시 로봇을 멈추고 예외 모드로 진입"""
        self.is_error = True
        
        # 재시도를 위해 로봇 상태(순응제어, 좌표계) 등 강제 초기화
        try:
            comp_off = self._action_map.get('compliance_off')
            if comp_off:
                comp_off.execute()
        except Exception as e:
            self.node.get_logger().error(f"상태 강제 초기화 중 무시된 오류: {e}")
            
        stop_action = self._action_map.get('stop')
        if stop_action:
            stop_action.execute()
            
        self.node.get_logger().error(f"🚨 [EMERGENCY] {action_name} 수행 중 실패! 시스템을 정지합니다.")