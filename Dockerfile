# 1. Base Image (ROS 2 Humble 기반)
FROM osrf/ros:humble-desktop

# 2. 필수 시스템 패키지 및 ROS 2 cv_bridge 설치
RUN apt-get update && apt-get install -y \
    python3-pip \
    ros-humble-rmw-cyclonedds-cpp \
    ros-humble-cv-bridge \
    ros-humble-sensor-msgs \
    && rm -rf /var/lib/apt/lists/*

# 3. YOLO 및 AI 관련 파이썬 라이브러리 설치
RUN pip3 install --no-cache-dir ultralytics "numpy<2" opencv-python

# 4. 워크스페이스 복사 및 빌드
WORKDIR /ros2_ws
COPY src/interfaces/od_msg ./src/interfaces/od_msg
COPY src/cobot2/object_detection ./src/cobot2/object_detection
RUN /bin/bash -c "source /opt/ros/humble/setup.bash && colcon build --symlink-install"

# 5. 실행 엔트리포인트 설정
COPY entrypoint.sh /
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
