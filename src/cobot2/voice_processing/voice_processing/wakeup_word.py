import os

import numpy as np
from ament_index_python.packages import get_package_share_directory
from openwakeword.model import Model
from scipy.signal import resample


package_path = get_package_share_directory("voice_processing")
MODEL_NAME = "wassup_homie.onnx"
MODEL_PATH = os.path.join(package_path, "resource", MODEL_NAME)
INFERENCE_FRAMEWORK = "onnx"


class WakeupWord:
    THRESHOLD = 0.001

    def __init__(self, buffer_size):
        # 🚨 유실되었던 모델 초기화 코드 복구
        self.model = Model(
            wakeword_models=[MODEL_PATH],
            inference_framework=INFERENCE_FRAMEWORK,
        )
        self.model_name = MODEL_NAME.split(".", maxsplit=1)[0]
        self.stream = None
        self.buffer_size = buffer_size
        self.last_confidence: float = 0.0

    def set_stream(self, stream):
        self.stream = stream

    def is_wakeup(self) -> bool:
        audio_chunk = np.frombuffer(
            self.stream.read(self.buffer_size, exception_on_overflow=False),
            dtype=np.int16,
        )
        audio_chunk = resample(audio_chunk, int(len(audio_chunk) * 16000 / 48000))
        outputs = self.model.predict(audio_chunk, threshold=0.1)
        self.last_confidence = float(outputs[self.model_name])
        print("confidence: ", self.last_confidence)
        if self.last_confidence > self.THRESHOLD:
            print("Wakeword detected!")
            return True
        return False