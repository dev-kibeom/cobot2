# 토픽:
#   /voice_command  (std_msgs/String)  - cobot_core/executer 가 받는 평면 JSON 시퀀스
#   /voice_reply    (std_msgs/String)  - 사용자에게 들려줄 자연어 reply

import json
import os
import threading
import time

import rclpy
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from rclpy.node import Node
from std_msgs.msg import String

from voice_processing.MicController import MicConfig, MicController
from voice_processing.stt import STT
from voice_processing.wakeup_word import WakeupWord


openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set. "
        "Add `export OPENAI_API_KEY=...` to ~/.bashrc and run `source ~/.bashrc`."
    )


class GetKeyword(Node):
    def __init__(self):
        prompt_content = """
        당신은 가정용 협동로봇의 음성 명령 파서다.
        사용자 발화를 단위 동작 시퀀스로 분해하고, 자연스러운 한국어 reply를 함께 생성한다.
        JSON만 출력. 다른 텍스트 금지.

        [출력 형식]
        {{
        "sequence": [{{"step": N, "action": "<액션>", "params": {{...}}}}],
        "reply": "한 문장"
        }}

        [액션 카탈로그]

        ▸ pick(object)   : 물체를 집는다.
        ▸ shake()        : 잡고 있는 물체를 흔든다. ★ pick 이후에만 사용.
        ▸ place(location): 지정 위치에 내려놓는다. ★ pick 이후에만 사용.
        ▸ reset()        : 홈 포지션으로 복귀한다 (그리퍼 열림). 모든 정상 시퀀스의 종료 동작.

        [지원 값]

        - object: "사과"
        - location: "쓰레기통"

        [규칙]

        1. 모든 정상 시퀀스는 마지막에 reset 으로 종료한다 (단순 홈 복귀 명령은 reset 단독).
        2. 한 시퀀스에 pick은 최대 1번.
        3. 카탈로그에 없는 액션이나 지원하지 않는 값을 요청하면 sequence는 [], reply는 거절 멘트.
        4. step 번호는 1부터 순차.

        [예시]

        사용자: "사과 버려줘"
        {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"place","params":{{"location":"쓰레기통"}}}},{{"step":3,"action":"reset","params":{{}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다."}}

        사용자: "사과 흔들어줘"
        {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"shake","params":{{}}}},{{"step":3,"action":"reset","params":{{}}}}],"reply":"네, 사과를 흔들어드릴게요."}}

        사용자: "사과 흔들고 쓰레기통에 버려"
        {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"shake","params":{{}}}},{{"step":3,"action":"place","params":{{"location":"쓰레기통"}}}},{{"step":4,"action":"reset","params":{{}}}}],"reply":"네, 사과를 흔들고 쓰레기통에 버리겠습니다."}}

        사용자: "홈으로 가"
        {{"sequence":[{{"step":1,"action":"reset","params":{{}}}}],"reply":"네, 홈 포지션으로 복귀하겠습니다."}}

        사용자: "컵 가져와"
        {{"sequence":[],"reply":"죄송합니다. 현재는 사과만 다룰 수 있어요."}}

        사용자: "그냥 흔들어"
        {{"sequence":[],"reply":"어떤 물건을 흔들까요?"}}

        <사용자 입력>
        "{user_input}"
        """

        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.0,
            openai_api_key=openai_api_key,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=prompt_content
        )
        self.lang_chain = self.prompt_template | self.llm
        self.stt = STT(openai_api_key=openai_api_key)

        super().__init__("get_keyword_node")

        mic_config = MicConfig(
            chunk=12000,
            rate=48000,
            channels=1,
            record_seconds=5,
            device_index=None,
            buffer_size=24000,
        )
        self.mic_controller = MicController(config=mic_config)
        self.wakeup_word = WakeupWord(buffer_size=mic_config.buffer_size)

        self.command_pub = self.create_publisher(String, "/voice_command", 10)
        self.reply_pub = self.create_publisher(String, "/voice_reply", 10)

        self.get_logger().info("get_keyword_node initialized.")
        self.get_logger().info("listening for wakeup word in background...")
        self.listen_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listen_thread.start()

    def _listen_loop(self):
        while rclpy.ok():
            try:
                self.mic_controller.open_stream()
                self.wakeup_word.set_stream(self.mic_controller.stream)
            except OSError as e:
                self.get_logger().error(f"mic stream error: {e}, retry in 3s")
                time.sleep(3)
                continue

            self.get_logger().info("waiting for wakeup word...")
            while rclpy.ok() and not self.wakeup_word.is_wakeup():
                time.sleep(0.01)
            if not rclpy.ok():
                break

            self.get_logger().info("wakeup detected, recording...")
            try:
                self.mic_controller.record_audio()
                wav_data = self.mic_controller.get_wav_data()
                self.mic_controller.close_stream()
            except Exception as e:
                self.get_logger().error(f"record error: {e}")
                self.mic_controller.close_stream()
                continue

            try:
                output_message = self.stt.speech2text(wav_data)
                self.get_logger().info(f"STT: {output_message}")

                sequence, reply = self.extract_keyword(output_message)
                self.get_logger().warn(f"sequence: {sequence}")
                self.get_logger().warn(f"reply: {reply}")

                cobot_seq = self._to_cobot_core_sequence(sequence)
                self.command_pub.publish(
                    String(data=json.dumps(cobot_seq, ensure_ascii=False))
                )
                self.reply_pub.publish(String(data=reply))
                self.get_logger().info("published /voice_command + /voice_reply")
            except json.JSONDecodeError as e:
                self.get_logger().error(f"LLM JSON parse error: {e}")
                self.reply_pub.publish(String(data="LLM 응답 파싱 실패"))
            except Exception as e:
                self.get_logger().error(f"unexpected: {e}")
                self.reply_pub.publish(String(data=f"error: {e}"))

    def extract_keyword(self, output_message):
        response = self.lang_chain.invoke({"user_input": output_message})
        result = json.loads(response.content)
        sequence = result.get("sequence", [])
        reply = str(result.get("reply", ""))
        return sequence, reply

    def _to_cobot_core_sequence(self, sequence):
        """
        프롬프트가 만드는 형식 -> cobot_core/executer 가 받는 평면 형식.
          [{"step":1,"action":"pick","params":{"object":"사과"}}, ...]
            ↓
          [{"action":"pick","params":{"target":"사과"}}, ...]
        - step 키 제거
        - params.object / params.location -> params.target 로 통일
        """
        out = []
        for step in sequence:
            action = step.get("action")
            params = step.get("params", {}) or {}
            if "object" in params:
                normalized = {"target": params["object"]}
            elif "location" in params:
                normalized = {"target": params["location"]}
            else:
                normalized = dict(params)
            out.append({"action": action, "params": normalized})
        return out


def main():
    rclpy.init()
    node = GetKeyword()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
