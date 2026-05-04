# /voice_command 토픽 (voice_processing_v2/get_keyword) 을 받아
# /execute_command 액션 (cobot_core/executer) 으로 전달하는 다리.
#
# 입력 토픽 메시지: std_msgs/String, JSON 평면 배열
#   예) [{"action":"pick","params":{"target":"사과"}},
#        {"action":"place","params":{"target":"쓰레기통"}}]
#
# 출력 액션 goal: command/action/Command
#   goal.command = 위 JSON 문자열 그대로

import json

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_msgs.msg import String

from command.action import Command


class SkillOrchestrator(Node):
    def __init__(self):
        super().__init__("skill_orchestrator")

        self._action_client = ActionClient(self, Command, "/execute_command")
        self._sub = self.create_subscription(
            String, "/voice_command", self._on_voice_command, 10
        )

        self.get_logger().info(
            "skill_orchestrator: subscribed to /voice_command, "
            "client of /execute_command"
        )

    def _on_voice_command(self, msg: String):
        try:
            sequence = json.loads(msg.data) if msg.data else []
        except json.JSONDecodeError as e:
            self.get_logger().error(f"voice_command JSON parse error: {e}")
            return

        if not sequence:
            self.get_logger().warn("empty sequence, skipping dispatch")
            return

        self.get_logger().info(
            f"received sequence ({len(sequence)} steps): {sequence}"
        )

        if not self._action_client.wait_for_server(timeout_sec=3.0):
            self.get_logger().error(
                "/execute_command action server unavailable - "
                "is cobot_core/executer running?"
            )
            return

        goal = Command.Goal()
        goal.command = msg.data

        send_future = self._action_client.send_goal_async(
            goal, feedback_callback=self._on_feedback
        )
        send_future.add_done_callback(self._on_goal_response)

    def _on_feedback(self, fb_msg):
        fb = fb_msg.feedback
        self.get_logger().info(
            f"feedback: step={fb.current_step} action={fb.current_action}"
        )

    def _on_goal_response(self, future):
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn("goal rejected by executer")
            return
        self.get_logger().info("goal accepted by executer")
        goal_handle.get_result_async().add_done_callback(self._on_result)

    def _on_result(self, future):
        result = future.result().result
        self.get_logger().info(
            f"result: success={result.success}, message='{result.message}'"
        )


def main(args=None):
    rclpy.init(args=args)
    node = SkillOrchestrator()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
