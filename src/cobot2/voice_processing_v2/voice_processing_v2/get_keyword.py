# ros2 service call /get_keyword od_msg/srv/SrvVoiceCmd "{}"

import json
import os
import time

import rclpy
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from rclpy.node import Node

from od_msg.srv import SrvVoiceCmd
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
        사용자 발화를 JSON 시퀀스로 변환하고, 사용자에게 들려줄 자연스러운 한국어 답변(reply)을 함께 생성한다.
        JSON 외 다른 출력은 금지한다.

        [출력 형식]
        {{
          "sequence": [
            {{"action": "<액션명>", "params": {{<파라미터>}}}}
          ],
          "reply": "사용자에게 들려줄 자연스러운 한국어 한 문장",
          "error": null
        }}

        [규칙]
        1. 사용자 의도를 카탈로그 액션의 조합으로 분해한다.
        2. `pick` 의 `params.target` 은 사용자가 발화한 한국어 객체명 그대로 둔다.
        3. 카탈로그에 명시되지 않은 액션은 절대 생성하지 않는다.
        4. 발화를 카탈로그로 표현할 수 없으면 sequence는 빈 배열, error에 사유를 넣고, reply에 사용자에게 들려줄 거절 멘트를 작성한다.
        5. 순서는 발화의 자연 순서를 따른다 (예: pick → goto_trash → gripper_open).
        6. reply는 정상 케이스에선 수행 의도를 확인시켜주는 한 문장, 에러 케이스에선 정중한 거절 한 문장으로 작성한다.
        7. JSON 만 출력한다. 설명·주석·markdown fence 금지.

        [액션 카탈로그]

        ▸ pick
          - input:  {{"target": "사과"}}
          - 설명:   객체를 탐지하고 집는다. 현재 target은 "사과"만 지원.

        ▸ goto_trash
          - input:  {{}}
          - 설명:   고정된 쓰레기통 위치로 이동.

        ▸ gripper_open
          - input:  {{}}
          - 설명:   그리퍼를 연다 (객체 놓기).

        ▸ gripper_close
          - input:  {{}}
          - 설명:   그리퍼를 닫는다.

        ▸ home
          - input:  {{}}
          - 설명:   홈 포지션으로 복귀.

        [현재 지원 시나리오]
        - "사과를 버려달라"는 명령만 정상 처리한다.
        - 그 외 객체 이동, 가져오기, 다른 위치 이동 등은 미지원으로 거절한다.

        [error 사유 분류]
        - "unsupported_action"  : 카탈로그에 없는 동작 요청
        - "unsupported_target"  : 사과가 아닌 다른 객체 요청
        - "ambiguous_command"   : 의도 파악 불가

        [예시]
        사용자: "사과 버려줘"
        출력: {{"sequence":[{{"action":"pick","params":{{"target":"사과"}}}},{{"action":"goto_trash","params":{{}}}},{{"action":"gripper_open","params":{{}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다.","error":null}}

        사용자: "저기 있는 사과 좀 치워줘"
        출력: {{"sequence":[{{"action":"pick","params":{{"target":"사과"}}}},{{"action":"goto_trash","params":{{}}}},{{"action":"gripper_open","params":{{}}}}],"reply":"네, 사과를 치워드릴게요.","error":null}}

        사용자: "썩은 사과 버려"
        출력: {{"sequence":[{{"action":"pick","params":{{"target":"사과"}}}},{{"action":"goto_trash","params":{{}}}},{{"action":"gripper_open","params":{{}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다.","error":null}}

        사용자: "그리퍼 닫아"
        출력: {{"sequence":[{{"action":"gripper_close","params":{{}}}}],"reply":"네, 그리퍼를 닫겠습니다.","error":null}}

        사용자: "홈으로 가"
        출력: {{"sequence":[{{"action":"home","params":{{}}}}],"reply":"네, 홈 포지션으로 복귀하겠습니다.","error":null}}

        사용자: "컵 가져와"
        출력: {{"sequence":[],"reply":"죄송합니다. 현재는 사과를 버리는 동작만 지원하고 있어요.","error":"unsupported_target"}}

        사용자: "춤춰봐"
        출력: {{"sequence":[],"reply":"죄송합니다. 지원하지 않는 명령이에요.","error":"unsupported_action"}}

        사용자: "어어 그거 좀"
        출력: {{"sequence":[],"reply":"죄송해요, 명령을 정확히 이해하지 못했어요. 다시 말씀해 주시겠어요?","error":"ambiguous_command"}}

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

        self.get_logger().info("MicRecorderNode initialized.")
        self.get_logger().info("wait for client's request...")
        self.get_keyword_srv = self.create_service(
            SrvVoiceCmd, "get_keyword", self.get_keyword
        )

    def extract_keyword(self, output_message):
        response = self.lang_chain.invoke({"user_input": output_message})
        result = json.loads(response.content)

        sequence = result.get("sequence", [])
        reply = str(result.get("reply", ""))
        error = result.get("error", None)

        print(f"sequence: {sequence}")
        print(f"reply   : {reply}")
        print(f"error   : {error}")

        return sequence, reply, error

    def get_keyword(self, request, response):
        try:
            print("open stream")
            self.mic_controller.open_stream()
            self.wakeup_word.set_stream(self.mic_controller.stream)

            while rclpy.ok() and not self.wakeup_word.is_wakeup():
                time.sleep(0.01)

            self.mic_controller.record_audio()
            wav_data = self.mic_controller.get_wav_data()
            self.mic_controller.close_stream()

            output_message = self.stt.speech2text(wav_data)
            self.get_logger().info(f"STT result: {output_message}")

            sequence, reply, error = self.extract_keyword(output_message)
            self.get_logger().warn(f"Generated sequence: {sequence}")
            self.get_logger().warn(f"Reply: {reply}")
            self.get_logger().warn(f"Error: {error}")

            response.success = error is None
            response.sequence_json = json.dumps(sequence, ensure_ascii=False)
            response.error = error if error else ""
            response.reply = reply
            return response

        except OSError as e:
            self.get_logger().error("Error: Failed to open audio stream")
            self.get_logger().error("please check your device index")
            self.mic_controller.close_stream()
            response.success = False
            response.sequence_json = "[]"
            response.error = "audio_device_error"
            response.reply = f"audio device error: {e}"
            return response
        except json.JSONDecodeError as e:
            self.get_logger().error(f"LLM JSON parse error: {e}")
            self.mic_controller.close_stream()
            response.success = False
            response.sequence_json = "[]"
            response.error = "llm_parse_error"
            response.reply = "LLM 응답 파싱 실패"
            return response
        except Exception as e:
            self.get_logger().error(f"unexpected error: {e}")
            self.mic_controller.close_stream()
            response.success = False
            response.sequence_json = "[]"
            response.error = "internal_error"
            response.reply = f"error: {e}"
            return response


def main():
    rclpy.init()
    node = GetKeyword()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
