import io
import wave
from dataclasses import dataclass

import pyaudio


@dataclass
class MicConfig:
    chunk: int = 12000
    rate: int = 48000
    channels: int = 1
    record_seconds: int = 5
    fmt: int = pyaudio.paInt16
    device_index: int = None
    buffer_size: int = 24000


class MicController:
    def __init__(self, config: MicConfig = MicConfig()):
        self.config = config
        self.audio = None
        self.stream = None
        self.sample_width = None
        self.frames = []

    def open_stream(self):
        self.audio = pyaudio.PyAudio()
        self.sample_width = self.audio.get_sample_size(self.config.fmt)
        kwargs = dict(
            format=self.config.fmt,
            channels=self.config.channels,
            rate=self.config.rate,
            input=True,
            frames_per_buffer=self.config.chunk,
        )
        if self.config.device_index is not None:
            kwargs["input_device_index"] = self.config.device_index
        self.stream = self.audio.open(**kwargs)

    def record_audio(self):
        self.frames = []
        num_chunks = int(self.config.rate / self.config.chunk * self.config.record_seconds)
        for _ in range(num_chunks):
            data = self.stream.read(self.config.chunk, exception_on_overflow=False)
            self.frames.append(data)

    def get_wav_data(self) -> bytes:
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(self.sample_width)
            wf.setframerate(self.config.rate)
            wf.writeframes(b"".join(self.frames))
        return wav_buffer.getvalue()

    def close_stream(self):
        if self.stream is not None:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
        if self.audio is not None:
            self.audio.terminate()
            self.audio = None
