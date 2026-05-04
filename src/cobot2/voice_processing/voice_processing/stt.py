
from openai import OpenAI

class STT:
    def __init__(self, openai_api_key):
        self.client = OpenAI(api_key=openai_api_key)
        
    def speech2text(self, audio_file_path):
        """
        MicController가 녹음해준 음성 파일을 받아 Whisper API로 텍스트화.
        """
        print("Whisper API에 음성 데이터 전송 중...")        

        # Whisper API 호출
        with open(audio_file_path, "rb") as f:
            transcript = self.client.audio.transcriptions.create(
                model="whisper-1", file=f)

        print("STT 결과: ", transcript.text)
        return transcript.text
