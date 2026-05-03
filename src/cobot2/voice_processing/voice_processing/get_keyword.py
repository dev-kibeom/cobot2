# ros2 service call /get_keyword std_srvs/srv/Trigger "{}"

import os
import rclpy
import pyaudio
import tempfile

from rclpy.node import Node

from ament_index_python.packages import get_package_share_directory
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
# from langchain.chains import LLMChain

from std_srvs.srv import Trigger

from voice_processing.MicController import MicController, MicConfig
from voice_processing.wakeup_word import WakeupWord
from voice_processing.stt import STT

############ Package Path & Environment Setting ############
current_dir = os.getcwd()
package_path = get_package_share_directory("voice_processing")

is_laod = load_dotenv(dotenv_path=os.path.join(package_path, ".env"))
openai_api_key = os.getenv("OPENAI_API_KEY")

############ AI Processor ############
# class AIProcessor:
#     def __init__(self):



############ GetKeyword Node ############
class GetKeyword(Node):
    def __init__(self):
        self.llm = ChatOpenAI(
            model="gpt-4o", temperature=0.5, openai_api_key=openai_api_key
        )

        prompt_content = """
        당신은 가정용 서비스 로봇의 행동을 제어하는 '작업 지시자(Task Planner)'입니다.
        사용자의 자연어 명령을 분석하여, 로봇이 순서대로 실행할 수 있는 JSON 배열 형태의 '동작 시퀀스'로 변환해야 합니다.

        <가용 자원 (현재 로봇이 인식/조작할 수 있는 한계)>
        - 조작 가능한 객체(Targets): "사과", "배", "바나나"
        - 수행 가능한 동작(Actions): 
          1. "pick" (객체를 집어 올림)
          2. "place" (객체를 내려놓음)
          3. "shake" (현재 잡고 있는 객체를 흔듦)
          4. "flip" (현재 잡고 있는 객체를 뒤집음)

        <작성 규칙>
        1. 출력은 반드시 JSON 배열(Array) 형식이어야 합니다.
        2. 배열의 각 요소는 "action"과 "params" 키를 가져야 합니다.
        3. "params" 내부에는 대상 객체를 지정하는 "target" 키가 들어갑니다. (단, 대상이 명확하지 않거나 이전 동작과 이어지는 경우 생략 가능)
        4. JSON 데이터 외에 어떠한 설명, 마크다운 코드 블록(```json 등), 인삿말도 출력하지 마세요. 오직 JSON 텍스트만 반환해야 파서가 고장 나지 않습니다.

        <예시 시나리오>
        입력: "사과 잡아서 흔들어줘" 
        출력: [{{"action": "pick", "params": {{"target": "사과"}}}}, {{"action": "shake", "params": {{}}}}]

        입력: "배를 뒤집어서 바나나 옆에 놔둬" 
        출력: [{{"action": "pick", "params": {{"target": "배"}}}}, {{"action": "flip", "params": {{}}}}, {{"action": "place", "params": {{"target": "바나나"}}}}]

        입력: "사과랑 바나나 둘 다 흔들어봐"
        출력: [{{"action": "pick", "params": {{"target": "사과"}}}}, {{"action": "shake", "params": {{}}}}, {{"action": "place", "params": {{"target": "사과"}}}}, {{"action": "pick", "params": {{"target": "바나나"}}}}, {{"action": "shake", "params": {{}}}}, {{"action": "place", "params": {{"target": "바나나"}}}}]

        <사용자 명령>
        "{user_input}"
        """

        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=prompt_content
        )
        self.lang_chain = self.prompt_template | self.llm
        # self.lang_chain = LLMChain(llm=self.llm, prompt=self.prompt_template)
        self.stt = STT(openai_api_key=openai_api_key)

        super().__init__("get_keyword_node")
        # 오디오 설정
        mic_config = MicConfig(
            chunk=12000,
            rate=48000,
            channels=1,
            record_seconds=5,
            fmt=pyaudio.paInt16,
            device_index=10,
            buffer_size=24000,
        )
        self.mic_controller = MicController(config=mic_config)
        # self.ai_processor = AIProcessor()

        self.get_logger().info("MicRecorderNode initialized.")
        self.get_logger().info("wait for client's request...")
        self.get_keyword_srv = self.create_service(
            Trigger, "get_keyword", self.get_keyword
        )
        self.wakeup_word = WakeupWord(mic_config.buffer_size)

    def extract_keyword(self, output_message):
        response = self.lang_chain.invoke({"user_input": output_message})
        result = response.content

        object, target = result.strip().split("/")

        object = object.split()
        target = target.split()

        print(f"llm's response: {object}")
        print(f"object: {object}")
        print(f"target: {target}")
        return object
    
    def get_keyword(self, request, response):  # 요청과 응답 객체를 받아야 함
        try:
            print("open stream")
            self.mic_controller.open_stream()
            self.wakeup_word.set_stream(self.mic_controller.stream)
        except OSError:
            self.get_logger().error("Error: Failed to open audio stream")
            self.get_logger().error("please check your device index")
            return response

        self.get_logger().info("Waiting for wakeup word...")
        while not self.wakeup_word.is_wakeup():
            pass

        # Wakeup Word 감지 직후, 열려있는 스트림을 이용하여 녹음 시작
        self.get_logger().info("[Wakeword detected] 네, 말씀하세요. ")
        self.mic_controller.record_audio()
        
        # 임시 저장 후 스트림 닫기
        temp_wav_path = "/tmp/command.wav"
        self.mic_controller.save_wav(temp_wav_path)
        self.mic_controller.close_stream()
        
        # STT --> Keword Extract --> Embedding
        output_message = self.stt.speech2text(temp_wav_path)
        keyword = self.extract_keyword(output_message)

        self.get_logger().warn(f"Detected targets: {keyword}")

        # 응답 객체 설정
        response.success = True
        response.message = " ".join(keyword)  # 감지된 키워드를 응답 메시지로 반환
        return response

def main():
    rclpy.init()
    node = GetKeyword()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
