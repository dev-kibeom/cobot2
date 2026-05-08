import os
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node

def generate_launch_description():
    # 1. 통합 파라미터 파일(params.yaml) 경로 가져오기
    bringup_dir = get_package_share_directory('cobot_bringup')
    params_file = os.path.join(bringup_dir, 'config', 'params.yaml')

    # 2. 실행할 노드들 정의
    
    # [로봇 제어 파트]
    executer_node = Node(
        package='cobot_core',
        executable='executer',  # setup.py의 entry_points에 등록된 이름
        name='executer',
        output='screen',
        parameters=[params_file]        # 🚨 yaml 파일 자동 주입
    )

    state_manager_node = Node(
        package='cobot_core',
        executable='state_manager',
        name='state_manager',
        output='screen',
        parameters=[params_file]
    )

    # [비전 파트]
    vision_node = Node(
        package='object_detection',
        executable='object_detection',
        name='object_detection',
        output='screen',
        parameters=[params_file]
    )

    # [음성 파트]
    voice_cmd_node = Node(
        package='voice_processing',
        executable='voice_to_command',
        name='voice_to_command',
        output='screen',
        parameters=[params_file]
    )

    voice_client_node = Node(
        package='voice_processing',
        executable='voice_client',
        name='voice_client',
        output='screen',
        parameters=[params_file]
    )

    # 3. 위에서 정의한 모든 노드를 하나의 Launch Description으로 묶어서 반환
    return LaunchDescription([
        executer_node,
        state_manager_node,
        vision_node,
        voice_cmd_node,
        voice_client_node
    ])