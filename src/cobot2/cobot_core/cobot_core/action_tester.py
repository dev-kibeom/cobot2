#!/usr/bin/env python3

import json
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import String


class TestVoiceCommand(Node):
    def __init__(self):
        super().__init__("test_voice_command")

        self.publisher = self.create_publisher(String, "/voice_command", 10)

        # state_manager가 subscription 준비할 시간 살짝 주기
        self.timer = self.create_timer(1.0, self.publish_once)
        self.published = False

    def publish_once(self):
        if self.published:
            return

        sequence = [
  {
    "action": "movesj",
    "params": {
      "joints": [[0, 90, 0, 0, 0, 0],[90,0,0,0,0,0]],
      "vel": 50,
      "acc": 50,
      "mode": "rel"
    },
    "desc": "1"
  },
  {
    "action": "wait",
    "params": {
      "time": 3.0
    },
    "desc": "2"
  },
  {
    "action": "reset",
    "desc": "reset"
  }
]

        msg = String()
        msg.data = json.dumps(sequence, ensure_ascii=False)

        self.publisher.publish(msg)
        self.get_logger().info(f"📤 /voice_command 테스트 시퀀스 전송 완료: {len(sequence)} steps")

        self.published = True


def main(args=None):
    rclpy.init(args=args)
    node = TestVoiceCommand()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()