import rclpy
import DR_init
import time
import json

from rclpy.node import Node
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.executors import MultiThreadedExecutor
from rcl_interfaces.msg import SetParametersResult
from rclpy.callback_groups import ReentrantCallbackGroup

from command.action import Command
from cobot_core.action_manager import ActionManager

class CommandExecuter(Node):
  def __init__(self):
    super().__init__('command_executer')
    
    # 파라미터 선언 및 기본값 설정
    self.declare_parameter('robot_id', 'dsr01')
    self.declare_parameter('robot_model', 'm0609')
    self.declare_parameter('robot_tool', 'Tool Weight')
    self.declare_parameter('robot_tcp', 'GripperDA_v1')
    self.declare_parameter('vel_linear', 200.0)
    self.declare_parameter('acc_linear', 50.0)
    self.declare_parameter('vel_angular', 70.0)
    self.declare_parameter('acc_angular', 70.0)
    self.declare_parameter('depth_offset', -35.0)
    self.declare_parameter('min_depth', 20.0)
        
    self._update_local_parameters()
    
    self.add_on_set_parameters_callback(self.parameter_update_callback)
    
    self.action_manager = ActionManager(node=self)
    self.action_cb_group = ReentrantCallbackGroup()
    
    self._action_server = ActionServer(
      self,
      Command,
      'execute_command',
      execute_callback=self.execute_callback,
      goal_callback=self.goal_callback,
      cancel_callback=self.cancel_callback,
      callback_group=self.action_cb_group
    )
    self.get_logger().info("🚀 Action Server Ready.")
    
  def init_dsr(self):
    """두산 로봇의 초기화 설정"""
    from DSR_ROBOT2 import set_tool, set_tcp,get_tool,get_tcp,ROBOT_MODE_MANUAL,ROBOT_MODE_AUTONOMOUS  # 필요한 기능만 임포트
    from DSR_ROBOT2 import get_robot_mode,set_robot_mode

    # Tool과 TCP 설정시 매뉴얼 모드로 변경해서 진행
    set_robot_mode(ROBOT_MODE_MANUAL)
    set_tool(self.robot_tool)
    set_tcp(self.robot_tcp)
    set_robot_mode(ROBOT_MODE_AUTONOMOUS)
    time.sleep(2)  # 설정 안정화를 위해 잠시 대기
    
    # 설정된 상수 출력
    print("#" * 50)
    print("Initializing robot with the following settings:")
    print(f"ROBOT_ID: {self.robot_id}")
    print(f"ROBOT_MODEL: {self.robot_model}")
    print(f"ROBOT_TCP: {get_tcp()}") 
    print(f"ROBOT_TOOL: {get_tool()}")
    print(f"ROBOT_MODE 0:수동, 1:자동 : {get_robot_mode()}")
    print("#" * 50)
    
  def goal_callback(self, goal_request):
    return GoalResponse.ACCEPT
  
  def cancel_callback(self, goal_handle):
    self.get_logger().warn("🛑 Cancel Request Received!")
    return CancelResponse.ACCEPT
  
  def execute_callback(self, goal_handle):
    """독립된 스레드에서 실제 로봇 동작 수행"""
    sequence = json.loads(goal_handle.request.command)
    result = Command.Result()
    feedback = Command.Feedback()
    
    self.action_manager.is_error = False
    self.action_manager.perform('clear_alarm')
    
    for i, step in enumerate(sequence):
      # 중단 요청 확인
      if goal_handle.is_cancel_requested:
        self.action_manager.perform('stop')
        goal_handle.canceled()
        
        result.success = False
        result.message = "Cancelled by user"
        return result
      
      # 피드백 업데이트
      feedback.current_step = i+1
      feedback.current_action = step.get('desc', step['action'])
      goal_handle.publish_feedback(feedback)
      
      self.get_logger().info(f"▶️ Executing: {feedback.current_action}")
      
      # 동작 실행 후 성공여부 확인
      success = self.action_manager.perform(step['action'], **step.get('params', {}))
      if not success:
        try:
          from DSR_ROBOT2 import get_current_posx, DR_BASE
          pos_list = get_current_posx(DR_BASE)[0] 
          pos_str = f" [멈춘 좌표: X:{pos_list[0]:.1f}, Y:{pos_list[1]:.1f}, Z:{pos_list[2]:.1f}]"
        except Exception as e:
          print(f"좌표 캡처 실패: {e}")
          pos_str = ""
          
        # ActionManage 내부에서 stop() 실행 후
        goal_handle.abort()
        result.success = False
        result.message = f"Error at step: {feedback.current_action}{pos_str}"
        return result
    
    goal_handle.succeed()
    result.success = True
    result.message = "Completed Successfully"
    return result
  
  def _update_local_parameters(self):
    """현재 노드의 파라미터 값을 멤버 변수로 동기화"""
    self.robot_id = self.get_parameter('robot_id').value
    self.robot_model = self.get_parameter('robot_model').value
    self.robot_tool = self.get_parameter('robot_tool').value
    self.robot_tcp = self.get_parameter('robot_tcp').value
    
    self.vel_linear = self.get_parameter('vel_linear').value
    self.acc_linear = self.get_parameter('acc_linear').value
    self.vel_angular = self.get_parameter('vel_angular').value
    self.acc_angular = self.get_parameter('acc_angular').value
    self.depth_offset = self.get_parameter('depth_offset').value
    self.min_depth = self.get_parameter('min_depth').value
        
  def parameter_update_callback(self, params):
    """rqt 등 외부에서 파라미터 변경 시 호출되는 콜백"""
    success = True
    for param in params:
        # 1. 값 검증 (예: 속도는 0보다 커야 함)
        if param.name in ['vel_linear', 'vel_angular', 'acc_linear', 'acc_angular']:
            if param.value <= 0:
                self.get_logger().warn(f"🚫 {param.name}은 0보다 커야 합니다. 변경을 거부합니다.")
                success = False
                continue
        
        # 2. 실시간 변수 업데이트
        if param.name == 'vel_linear':
            self.vel_linear = param.value
        elif param.name == 'acc_linear':
            self.acc_linear = param.value
        elif param.name == 'vel_angular':
            self.vel_angular = param.value
        elif param.name == 'acc_angular':
            self.acc_angular = param.value
        elif param.name == 'depth_offset':
            self.depth_offset = param.value
        elif param.name == 'min_depth':
            self.min_depth = param.value
            
        self.get_logger().info(f"⚙️ 파라미터 변경 완료: {param.name} -> {param.value}")
        
    return SetParametersResult(successful=success)
    
def main(args=None):
    rclpy.init(args=args)
    
    temp_node = Node('command_executer')
    temp_node.declare_parameter('robot_id', 'dsr01')
    temp_node.declare_parameter('robot_model', 'm0609')
    robot_id = temp_node.get_parameter('robot_id').value
    robot_model = temp_node.get_parameter('robot_model').value
    temp_node.destroy_node()
    
    import DR_init
    DR_init.__dsr__id = robot_id
    DR_init.__dsr__model = robot_model
    dsr_node = Node('dsr_helper_node', namespace=robot_id)
    DR_init.__dsr__node = dsr_node
    
    node = CommandExecuter()
    
    # DR_init.__dsr__id = node.robot_id
    # DR_init.__dsr__model = node.robot_model

    # # DSR 내부 통신을 전담할 더미헬퍼 노드
    # dsr_node = Node('dsr_helper_node', namespace=node.robot_id)
    # DR_init.__dsr__node = dsr_node
    
    try:
      # 전역적으로 DSR_ROBOT2 로드 시도
      import DSR_ROBOT2
      node.init_dsr()
    except Exception as e:
      print(f"DSR_ROBOT2 Load Error: {e}")
      
    executor = MultiThreadedExecutor(num_threads=4)   
    executor.add_node(dsr_node)
    executor.add_node(node)
    
    try:
      executor.spin()
    except KeyboardInterrupt:
        print("\nKeyboard interrupted by user. Shutting down...")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    finally:
      node.destroy_node()
      rclpy.shutdown()

if __name__ == "__main__":
    main()