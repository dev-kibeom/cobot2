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

from voice_processing_v2.MicController import MicConfig, MicController
from voice_processing_v2.stt import STT
from voice_processing_v2.wakeup_word import WakeupWord


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
        사용자 발화를 단위 동작들의 조합으로 분해한 JSON 시퀀스로 변환하고,
        사용자에게 들려줄 자연스러운 한국어 답변(reply)을 함께 생성한다.
        JSON 외 다른 출력은 금지한다.

        [출력 형식]
        {{
          "sequence": [
            {{"step": 1, "action": "<액션명>", "params": {{<파라미터>}}}}
          ],
          "reply": "사용자에게 들려줄 자연스러운 한국어 한 문장"
        }}

        [규칙]
        1. 사용자 의도를 카탈로그 액션의 조합으로 분해한다.
        2. 각 step은 1부터 시작해 순차적으로 번호를 매긴다.
        3. `pick` 의 `params.object` 는 [지원 object] 목록 중 하나여야 한다.
        4. `place` 의 `params.location` 은 [지원 location] 목록 중 하나여야 한다.
        5. 카탈로그에 명시되지 않은 액션은 절대 생성하지 않는다.
        6. 모든 정상 시퀀스는 마지막에 `place(홈)` 으로 종료한다 (자동 홈 복귀).
           단, 단순 "홈으로 가" 명령은 그 자체로 종료.
        7. 발화를 카탈로그로 표현할 수 없거나, 지원하지 않는 객체/위치를 요청하면
           sequence는 빈 배열 `[]` 로 두고 reply에 정중한 거절 멘트를 작성한다.
        8. 순서는 발화의 자연 순서를 따른다 (예: 버리기 = pick(사과) → place(쓰레기통) → place(홈)).
        9. reply는 정상 케이스에선 수행 의도를 확인시켜주는 한 문장,
           거절 케이스에선 무엇을 못 하는지 알려주는 한 문장으로 작성한다.
        10. JSON 만 출력한다. 설명·주석·markdown fence 금지.

        [액션 카탈로그]

        ▸ pick
          - input:  {{"object": "<물체명>"}}
          - 설명:   지정 물체로 이동 후 집는다 (탐지+이동+그립 통합 단위 동작).
          - 발화 예: "집어", "잡아", "들어"

        ▸ place
          - input:  {{"location": "<위치명>"}}
          - 설명:   지정 위치로 이동 후 내려놓는다 (이동+그리퍼 열기 통합 단위 동작).
          - 발화 예: "놓아", "내려놔", "둬", "버려" (쓰레기통), "복귀" (홈)

        [지원 object]
        - "사과"

        [지원 location]
        - "쓰레기통"
        - "홈"

        [예시]

        ▶ 정상 시나리오 - 버리기 (가장 일반적)
        사용자: "사과 버려줘"
        출력: {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"place","params":{{"location":"쓰레기통"}}}},{{"step":3,"action":"place","params":{{"location":"홈"}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다."}}

        사용자: "저기 있는 사과 좀 치워줘"
        출력: {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"place","params":{{"location":"쓰레기통"}}}},{{"step":3,"action":"place","params":{{"location":"홈"}}}}],"reply":"네, 사과를 치워드릴게요."}}

        사용자: "썩은 사과 버려"
        출력: {{"sequence":[{{"step":1,"action":"pick","params":{{"object":"사과"}}}},{{"step":2,"action":"place","params":{{"location":"쓰레기통"}}}},{{"step":3,"action":"place","params":{{"location":"홈"}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다."}}

        ▶ 단순 홈 복귀
        사용자: "홈으로 가"
        출력: {{"sequence":[{{"step":1,"action":"place","params":{{"location":"홈"}}}}],"reply":"네, 홈 포지션으로 복귀하겠습니다."}}

        사용자: "원위치"
        출력: {{"sequence":[{{"step":1,"action":"place","params":{{"location":"홈"}}}}],"reply":"네, 원위치로 돌아갈게요."}}

        ▶ 거절 시나리오
        사용자: "컵 가져와"
        출력: {{"sequence":[],"reply":"죄송합니다. 현재는 사과만 다룰 수 있어요."}}

        사용자: "사과 싱크대에 놔"
        출력: {{"sequence":[],"reply":"죄송합니다. 현재 사과는 쓰레기통에만 놓을 수 있어요."}}

        사용자: "춤춰봐"
        출력: {{"sequence":[],"reply":"죄송합니다. 지원하지 않는 명령이에요."}}

        사용자: "그냥 집어"
        출력: {{"sequence":[],"reply":"어떤 물건을 집을까요? 정확하게 말씀해 주세요."}}

        사용자: "어어 그거 좀"
        출력: {{"sequence":[],"reply":"죄송해요, 명령을 정확히 이해하지 못했어요. 다시 말씀해 주시겠어요?"}}

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
