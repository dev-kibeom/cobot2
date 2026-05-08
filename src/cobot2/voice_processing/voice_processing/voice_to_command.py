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
from voice_processing.prompt import PROMPT_CONTENT
from voice_processing.stt import STT
from voice_processing.wakeup_word import WakeupWord


openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set. "
        "Add `export OPENAI_API_KEY=...` to ~/.bashrc and run `source ~/.bashrc`."
    )


class VoiceToCommand(Node):
    def __init__(self):
        super().__init__("voice_to_command")
        
        self.declare_parameter('mic_chunk', 12000)
        self.declare_parameter('mic_rate', 48000)
        self.declare_parameter('record_seconds', 5)
        self.declare_parameter('llm_model', 'gpt-4o')
        self.declare_parameter('llm_temperature', 0.0)
        # (wakeup 관련 파라미터는 생략, 필요시 동일하게 추가 가능)
        
        llm_model = self.get_parameter('llm_model').value
        llm_temp = self.get_parameter('llm_temperature').value
        
        # ====================== 노드 통신 ====================== #
        self.command_pub = self.create_publisher(String, '/voice_command',   10)
        self.wakeup_pub  = self.create_publisher(String, '/wakeup_status',   10)
        self.stt_pub     = self.create_publisher(String, '/stt_result',      10)
        self.reply_pub   = self.create_publisher(String, '/voice_reply',     10)
        self.create_subscription(String, '/status', self._on_status, 10)
        # ===================================================== #

        self.robot_busy = False  # state_manager state != "IDLE" 이면 True

        self.llm = ChatOpenAI(
            model=llm_model,
            temperature=llm_temp,
            openai_api_key=openai_api_key,
            model_kwargs={"response_format": {"type": "json_object"}},
        )
        self.prompt_template = PromptTemplate(
            input_variables=["user_input"], template=PROMPT_CONTENT
        )
        self.lang_chain = self.prompt_template | self.llm
        self.stt = STT(openai_api_key=openai_api_key)

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

        self.get_logger().info("voice_to_command initialized.")
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

            self.get_logger().info("💤 'What's up, Hommie!' 웨이크업 워드 대기 중...")

            # wakeup_word 감지 루프 — confidence 실시간 발행
            while rclpy.ok():
                detected = self.wakeup_word.is_wakeup()
                self._publish_wakeup(detected)
                if not detected:
                    continue

                # 로봇 동작 중이면 안내만 하고 wakeup 다시 대기
                if self.robot_busy:
                    self.get_logger().warn("⚠️ 로봇 동작 중 - wakeup 무시")
                    self.reply_pub.publish(String(data="잠시만요, 지금 동작 중입니다."))
                    time.sleep(3.0)  # TTS 재생 + 마이크 안정화 시간
                    continue

                break

            if not rclpy.ok():
                break

            self.get_logger().info("🌟 [웨이크업 감지] 네, 말씀하세요!")
            
            # 5초간 녹음 (별도 스레드라 ROS 메인루프에 영향 없음)
            self.mic_controller.record_audio()
            wav_data = self.mic_controller.get_wav_data()
            self.mic_controller.close_stream()

            self.get_logger().info("🧠 STT 및 LLM 분석 중...")
            
            try:
                # 1. STT 변환 및 발행
                output_message = self.stt.speech2text(wav_data)
                self.get_logger().info(f"🗣️ STT 인식 결과: {output_message}")
                self.stt_pub.publish(String(data=output_message))

                # 2. LLM을 통해 시퀀스와 응답 추출
                sequence, reply = self.extract_keyword(output_message)
                self.get_logger().warn(f"로봇 동작 시퀀스: {sequence}")
                self.get_logger().warn(f"로봇 음성 응답: {reply}")

                # 3. /voice_command 토픽 발행 (Executer 용)
                cmd_msg = String()
                cmd_msg.data = json.dumps(sequence, ensure_ascii=False)
                self.command_pub.publish(cmd_msg)

                # 4. /voice_reply 토픽 발행 (Voice Client TTS 용)
                reply_msg = String()
                reply_msg.data = reply
                self.reply_pub.publish(reply_msg)
                
                self.get_logger().info("✅ 명령어 및 응답 발행 완료!\n" + "="*40)
                
            except json.JSONDecodeError as e:
                self.get_logger().error(f"❌ LLM JSON 파싱 실패: {e}")
                self.reply_pub.publish(String(data="명령을 이해하지 못했습니다. 다시 말씀해 주세요."))
            except Exception as e:
                self.get_logger().error(f"❌ 처리 중 예외 발생: {e}")
                self.reply_pub.publish(String(data="시스템 에러가 발생했습니다."))
        
    def _publish_wakeup(self, detected: bool):
        """순수하게 웨이크업 상태만 퍼블리시하는 함수로 원상복구"""
        msg = String()
        msg.data = json.dumps({
            'type':       'wakeup',
            'wake_word':  'whatsup homie',
            'confidence': self.wakeup_word.last_confidence,
            'detected':   detected,
        }, ensure_ascii=False)
        self.wakeup_pub.publish(msg)
            
    def _on_status(self, msg):
        """state_manager 상태 받아서 robot_busy 갱신"""
        try:
            data = json.loads(msg.data)
            self.robot_busy = (data.get("state") != "IDLE")
        except Exception:
            pass

    def extract_keyword(self, output_message):
        """LLM 응답을 sequence와 reply로 분리"""
        response = self.lang_chain.invoke({"user_input": output_message})
        result = json.loads(response.content)
        sequence = result.get("sequence", [])
        reply = str(result.get("reply", ""))
        return sequence, reply

def main():
    rclpy.init()
    node = VoiceToCommand()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()