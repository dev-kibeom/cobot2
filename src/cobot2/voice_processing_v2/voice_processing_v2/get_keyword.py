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
        당신은 사용자의 발화에서 [과일]과 [목적지]를 추출하고,
        사용자에게 들려줄 자연스러운 한국어 답변(reply)을 함께 생성합니다.

        <과일 후보> 사과, 배, 바나나, 오렌지
        <목적지 후보> pos1, pos2, pos3

        <출력 형식>
        반드시 다음 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
        {{
          "objects": ["..."],
          "targets": ["..."],
          "reply": "사용자에게 들려줄 자연스러운 한국어 한 문장"
        }}

        <규칙>
        - 과일이 없으면 objects는 빈 배열 []
        - 목적지가 없으면 targets는 빈 배열 []
        - 과일과 목적지의 순서는 발화 등장 순서를 따릅니다.
        - 명확한 명칭이 없어도 문맥상 유추 가능하면 후보 중 가장 가까운 항목을 선택하세요.
          (예: "길쭉하고 노란 과일" -> 바나나, "아침에 먹는 빨간 과일" -> 사과)
        - reply는 추출 결과를 사용자에게 확인시켜주는 한 문장으로 작성하세요.

        <예시>
        입력: "사과를 pos1에 가져다 놔"
        출력: {{"objects": ["사과"], "targets": ["pos1"], "reply": "네, 사과를 pos1로 옮기겠습니다."}}

        입력: "왼쪽에 있는 배와 오렌지를 pos1에 넣어줘"
        출력: {{"objects": ["배", "오렌지"], "targets": ["pos1"], "reply": "네, 배와 오렌지를 pos1에 넣겠습니다."}}

        입력: "오른쪽에 있는 바나나를 줘"
        출력: {{"objects": ["바나나"], "targets": [], "reply": "네, 바나나를 가져다 드릴게요."}}

        입력: "사과 집어줘"
        출력: {{"objects": ["사과"], "targets": [], "reply": "네, 사과를 집어드릴게요."}}

        입력: "배는 pos2에 두고 오렌지는 pos1에 둬"
        출력: {{"objects": ["배", "오렌지"], "targets": ["pos2", "pos1"], "reply": "네, 배는 pos2에, 오렌지는 pos1에 두겠습니다."}}

        <사용자 입력>
        "{user_input}"
        """

        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0.2,
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

        objects = [str(x) for x in result.get("objects", [])]
        targets = [str(x) for x in result.get("targets", [])]
        reply = str(result.get("reply", ""))

        print(f"objects: {objects}")
        print(f"targets: {targets}")
        print(f"reply  : {reply}")

        return objects, targets, reply

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

            objects, targets, reply = self.extract_keyword(output_message)
            self.get_logger().warn(f"Detected objects: {objects}")
            self.get_logger().warn(f"Detected targets: {targets}")

            response.success = True
            response.objects = objects
            response.targets = targets
            response.reply = reply
            return response

        except OSError as e:
            self.get_logger().error("Error: Failed to open audio stream")
            self.get_logger().error("please check your device index")
            self.mic_controller.close_stream()
            response.success = False
            response.reply = f"audio device error: {e}"
            return response
        except json.JSONDecodeError as e:
            self.get_logger().error(f"LLM JSON parse error: {e}")
            self.mic_controller.close_stream()
            response.success = False
            response.reply = "LLM 응답 파싱 실패"
            return response
        except Exception as e:
            self.get_logger().error(f"unexpected error: {e}")
            self.mic_controller.close_stream()
            response.success = False
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
