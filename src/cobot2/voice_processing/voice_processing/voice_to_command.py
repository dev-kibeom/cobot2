# ros2 service call /get_keyword std_srvs/srv/Trigger "{}"

import os
import time
import rclpy
import pyaudio
import threading

from rclpy.node import Node
from std_msgs.msg import String

from ament_index_python.packages import get_package_share_directory
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate

from voice_processing.stt import STT
from voice_processing.wakeup_word import WakeupWord
from voice_processing.mic_controller import MicController, MicConfig

############ Package Path & Environment Setting ############
current_dir = os.getcwd()
package_path = get_package_share_directory("voice_processing")

is_laod = load_dotenv(dotenv_path=os.path.join(package_path, ".env"))
openai_api_key = os.getenv("OPENAI_API_KEY")


class VoiceToCommand(Node):
    def __init__(self):
        super().__init__("get_keyword_node")
        
        # ====================== 노드 통신 ====================== #
        self.command_pub = self.create_publisher(String, '/voice_command', 10)
        # ===================================================== #
        
        self.llm = ChatOpenAI(
            model="gpt-4o", temperature=0.2, openai_api_key=openai_api_key
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
        self.wakeup_word = WakeupWord(mic_config.buffer_size)

        # 블로킹 방지를 위한 리스닝 스레드 시작
        self.get_logger().info("👂 Voice Processing Node가 백그라운드에서 듣기를 시작합니다...")
        self.listen_thread = threading.Thread(target=self.continuous_listen, daemon=True)
        self.listen_thread.start()

    def continuous_listen(self):
        """wakeup word를 무한 대기하며 퍼블리싱"""
        while rclpy.ok():
            try:
                self.mic_controller.open_stream()
                self.wakeup_word.set_stream(self.mic_controller.stream)
            except OSError:
                self.get_logger().error("마이크 스트림 에러. 3초 후 재시도합니다.")
                time.sleep(3)
                continue

            self.get_logger().info("💤 'Hello Rokey' 웨이크업 워드 대기 중...")
            
            # wakeup_word 감지루프
            while not self.wakeup_word.is_wakeup() and rclpy.ok():
                pass
            
            if not rclpy.ok():
                break
            
            self.get_logger().info("🌟 [웨이크업 감지] 네, 말씀하세요!")
            self.mic_controller.record_audio()
            
            temp_wav_path = "/tmp/command.wav"
            self.mic_controller.save_wav(temp_wav_path)
            
            # STT 수행 전에 자원 충돌방지를 위해 마이크 스트림 닫기
            self.mic_controller.close_stream()
            
            self.get_logger().info("🧠 STT 및 LLM 분석 중...")
            output_message = self.stt.speech2text(temp_wav_path)
            
            # LLM 체인 실행
            response = self.lang_chain.invoke({"user_input": output_message})
            sequence_json = response.content.strip()
            
            self.get_logger().warn(f"LLM 출력결과:\n{sequence_json}")
            
            # 추출된 JSON 시퀸스를 토픽으로 발행
            msg = String()
            msg.data = sequence_json
            self.command_pub.publish(msg)
            self.get_logger().info("✅ /voice_command 토픽으로 JSON 시퀀스 발행 완료!")
        
def main():
    rclpy.init()
    node = VoiceToCommand()
    
    try:
        # spin은 다른 노드 통신 처리를 위해 그대로 둠 (오디오 처리는 스레드가 담당)
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("프로그램을 종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
