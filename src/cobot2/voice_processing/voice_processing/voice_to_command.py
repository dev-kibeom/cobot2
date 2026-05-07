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


class VoiceToCommand(Node):
    def __init__(self):
        super().__init__("voice_to_command")
        
        # ====================== 노드 통신 ====================== #
        self.command_pub = self.create_publisher(String, '/voice_command',   10)
        self.wakeup_pub  = self.create_publisher(String, '/wakeup_status',   10)
        self.stt_pub     = self.create_publisher(String, '/stt_result',      10)
        self.reply_pub   = self.create_publisher(String, '/voice_reply',     10)
        # ===================================================== #
        
        prompt_content = """
        당신은 가정용 협동로봇의 음성 명령 파서다.
        사용자 발화를 단위 동작 시퀀스로 분해하고, 자연스러운 한국어 reply를 함께 생성한다.
        JSON만 출력. 다른 텍스트 금지.

        [출력 형식]
        {{
        "sequence": [{{"step": N, "action": "<액션>", "params": {{"target": "<값>"}} 또는 {{}}}}],
        "reply": "한 문장"
        }}

        [액션 카탈로그]

        ▸ pick(target)            : 물체를 수직으로 집는다.
        ▸ pick_horizontal(target) : 물체를 수평으로 집는다.
        ▸ finding(target)         : 물체 위치를 탐색한다. "어디있어", "찾아봐" 같은 단독 탐색 발화 시.
        ▸ place(target)           : 지정 위치에 내려놓는다. ★ pick / pick_horizontal 이후에만 사용.
        ▸ shake()                 : 잡고 있는 물체를 흔든다. ★ pick / pick_horizontal 이후에만 사용.
        ▸ reset()                 : 홈 포지션으로 복귀한다 (그리퍼 열림). 모든 정상 시퀀스의 종료 동작.

        [지원 값 (params.target 키로 발행)]

        - 객체 (한국어 발화 → 영어로 발행):
          · "사과"   → "apple"   (★ 항상 pick 으로 잡는다)
          · "후추통" → "shaker"  (★ 항상 pick_horizontal 으로 잡는다)
        - 위치 (한국어 그대로 발행):
          · "쓰레기통"

        [규칙]

        1. 객체별 잡는 방식은 고정이다. 사용자 발화의 "수직"/"수평"/"가로" 같은 단어와 무관하게:
           - apple → 항상 pick
           - shaker → 항상 pick_horizontal
        2. 모든 정상 시퀀스는 마지막에 reset 으로 종료한다 (단순 홈 복귀 / 단순 finding 발화는 단독).
        3. 한 시퀀스에 pick / pick_horizontal 은 합쳐 최대 1번.
        4. params 는 항상 {{"target": ...}} 형식. 액션 자체가 인자 없으면 {{}}.
        5. 객체는 영어(apple/shaker)로, 위치는 한국어(쓰레기통)로 발행.
        6. 카탈로그에 없는 액션이나 지원하지 않는 값을 요청하면 sequence 는 [], reply 는 거절 멘트.
        7. step 번호는 1부터 순차.

        [예시]

        사용자: "사과 버려줘"
        {{"sequence":[{{"step":1,"action":"pick","params":{{"target":"apple"}}}},{{"step":2,"action":"place","params":{{"target":"쓰레기통"}}}},{{"step":3,"action":"reset","params":{{}}}}],"reply":"네, 사과를 쓰레기통에 버리겠습니다."}}

        사용자: "후추통 잡아"
        {{"sequence":[{{"step":1,"action":"pick_horizontal","params":{{"target":"shaker"}}}},{{"step":2,"action":"reset","params":{{}}}}],"reply":"네, 후추통을 잡겠습니다."}}

        사용자: "후추통 흔들어"
        {{"sequence":[{{"step":1,"action":"pick_horizontal","params":{{"target":"shaker"}}}},{{"step":2,"action":"shake","params":{{}}}},{{"step":3,"action":"reset","params":{{}}}}],"reply":"네, 후추통을 흔들겠습니다."}}

        사용자: "사과 흔들고 쓰레기통에 버려"
        {{"sequence":[{{"step":1,"action":"pick","params":{{"target":"apple"}}}},{{"step":2,"action":"shake","params":{{}}}},{{"step":3,"action":"place","params":{{"target":"쓰레기통"}}}},{{"step":4,"action":"reset","params":{{}}}}],"reply":"네, 사과를 흔들고 쓰레기통에 버리겠습니다."}}

        사용자: "사과 어디있어"
        {{"sequence":[{{"step":1,"action":"finding","params":{{"target":"apple"}}}}],"reply":"사과를 찾아볼게요."}}

        사용자: "홈으로 가"
        {{"sequence":[{{"step":1,"action":"reset","params":{{}}}}],"reply":"네, 홈 포지션으로 복귀하겠습니다."}}

        사용자: "컵 가져와"
        {{"sequence":[],"reply":"죄송합니다. 현재는 사과와 후추통만 다룰 수 있어요."}}

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
                if detected:
                    break

            if not rclpy.ok():
                break

            self.get_logger().info("🌟 [웨이크업 감지] 네, 말씀하세요!")
            self.mic_controller.record_audio()

            # 🚨 수정된 부분: 파일을 임시 저장하지 않고 메모리(bytes)로 직접 받아 STT에 전달
            wav_data = self.mic_controller.get_wav_data()

            # STT 수행 전에 자원 충돌방지를 위해 마이크 스트림 닫기
            self.mic_controller.close_stream()

            self.get_logger().info("🧠 STT 및 LLM 분석 중...")
            try:
                output_message = self.stt.speech2text(wav_data)
                self.get_logger().info(f"STT: {output_message}")
                self.stt_pub.publish(String(data=output_message))

                sequence, reply = self.extract_keyword(output_message)
                self.get_logger().warn(f"sequence: {sequence}")
                self.get_logger().warn(f"reply: {reply}")

                cobot_seq = self._to_cobot_core_sequence(sequence)
                self.command_pub.publish(
                    String(data=json.dumps(cobot_seq, ensure_ascii=False))
                )
                self.reply_pub.publish(String(data=reply))
                self.get_logger().info("✅ /voice_command + /voice_reply 발행 완료")
            except json.JSONDecodeError as e:
                self.get_logger().error(f"LLM JSON parse error: {e}")
                self.reply_pub.publish(String(data="LLM 응답 파싱 실패"))
            except Exception as e:
                self.get_logger().error(f"unexpected: {e}")
                self.reply_pub.publish(String(data=f"error: {e}"))
        
    def _publish_wakeup(self, detected: bool):
        msg = String()
        msg.data = json.dumps({
            'type':       'wakeup',
            'wake_word':  'hello rokey',
            'confidence': self.wakeup_word.last_confidence,
            'detected':   detected,
        }, ensure_ascii=False)
        self.wakeup_pub.publish(msg)

    def extract_keyword(self, output_message):
        """LLM 응답을 sequence와 reply로 분리"""
        response = self.lang_chain.invoke({"user_input": output_message})
        result = json.loads(response.content)
        sequence = result.get("sequence", [])
        reply = str(result.get("reply", ""))
        return sequence, reply

    def _to_cobot_core_sequence(self, sequence):
        """프롬프트 형식 -> state_manager가 받는 평면 형식.
          [{"step":1,"action":"pick","params":{"object":"사과"}}, ...]
            ↓
          [{"action":"pick","params":{"target":"사과"}}, ...]
        - step 키 제거
        - params.object / params.location -> params.target 통일
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