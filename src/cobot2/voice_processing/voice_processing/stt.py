import io

from openai import OpenAI


class STT:
    def __init__(self, openai_api_key):
        self.client = OpenAI(api_key=openai_api_key)

    def speech2text(self, wav_data):
        wav_buffer = io.BytesIO(wav_data)
        wav_buffer.name = "audio.wav"
        transcript = self.client.audio.transcriptions.create(
            model="whisper-1", file=wav_buffer
        )
        return transcript.text
