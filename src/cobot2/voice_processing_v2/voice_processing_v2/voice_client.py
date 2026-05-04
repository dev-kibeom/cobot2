# 사용 예: ros2 run voice_processing_v2 voice_client
# tts

import os
import subprocess
import tempfile
import time

import rclpy
from openai import OpenAI
from rclpy.node import Node

from od_msg.srv import SrvVoiceCmd


openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise RuntimeError(
        "OPENAI_API_KEY environment variable is not set. "
        "Add `export OPENAI_API_KEY=...` to ~/.bashrc and run `source ~/.bashrc`."
    )

_openai_client = OpenAI(api_key=openai_api_key)


def speak(text: str, voice: str = "nova", model: str = "tts-1"):
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

        self.client = self.create_client(SrvVoiceCmd, "get_keyword")
        while not self.client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("waiting for /get_keyword service...")

        self.get_logger().info("voice_client connected to /get_keyword.")

    def request_voice(self):
        request = SrvVoiceCmd.Request()
        future = self.client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        return future.result()

def main():
    rclpy.init()
    node = VoiceClient()

    print("\n=== voice_client started (자동 반복 모드, Ctrl+C로 종료) ===\n")

    try:
        while rclpy.ok():
            print("[대기] '헬로 로키' 호출어를 외쳐주세요...\n")

            response = node.request_voice()
            if response is None:
                node.get_logger().error("no response from /get_keyword")
                continue

            if not response.success:
                node.get_logger().warn(f"failed: {response.reply}")
                speak(response.reply)
                continue

            print("=" * 50)
            print(f"  objects: {list(response.objects)}")
            print(f"  targets: {list(response.targets)}")
            print(f"  reply  : {response.reply}")
            print("=" * 50 + "\n")

            speak(response.reply)
            time.sleep(0.5)

    except (KeyboardInterrupt, EOFError):
        print("\n종료합니다.")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
