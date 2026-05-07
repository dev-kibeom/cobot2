# 사용 예: ros2 run voice_processing voice_client
# /voice_command (JSON 시퀀스) 와 /voice_reply (자연어) 토픽을 구독하고
# reply 를 OpenAI TTS 로 재생.

import os
import subprocess
import tempfile

import rclpy
from openai import OpenAI
from rclpy.node import Node
from std_msgs.msg import String


openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set. "
        "Add `export OPENAI_API_KEY=...` to ~/.bashrc and run `source ~/.bashrc`."
    )

_openai_client = OpenAI(api_key=openai_api_key)


def speak(text: str, voice: str = "onyx", model: str = "tts-1"):
    """OpenAI TTS로 텍스트를 음성 합성 후 mpg123으로 재생."""
    if not text:
        return
    mp3_path = None
    try:
        response = _openai_client.audio.speech.create(
            model=model,
            voice=voice,
            input=text,
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(response.content)
            mp3_path = f.name

        subprocess.run(
            ["mpg123", "-q", mp3_path],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"[TTS error] {e}")
    finally:
        if mp3_path:
            try:
                os.remove(mp3_path)
            except Exception:
                pass


class VoiceClient(Node):
    def __init__(self):
        super().__init__("voice_client_node")
        
        self.declare_parameter('tts_model', 'tts-1')
        self.declare_parameter('tts_voice', 'onyx')
        
        self.tts_model = self.get_parameter('tts_model').value
        self.tts_voice = self.get_parameter('tts_voice').value

        self.create_subscription(String, "/voice_command", self._on_command, 10)
        self.create_subscription(String, "/voice_reply", self._on_reply, 10)

        self.get_logger().info(
            "voice_client subscribed to /voice_command, /voice_reply"
        )

    def _on_command(self, msg: String):
        print("=" * 50)
        print(f"  /voice_command : {msg.data}")
        print("=" * 50)

    def _on_reply(self, msg: String):
        text = msg.data
        print(f"  /voice_reply   : {text}")
        speak(text, voice=self.tts_voice, model=self.tts_model)


def main():
    rclpy.init()
    node = VoiceClient()

    print("\n=== voice_client started (자동 반복 모드, Ctrl+C로 종료) ===\n")

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, EOFError):
        print("\n종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
