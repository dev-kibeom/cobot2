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
    def __init__(self, buffer_size, threshold=0.3):
        self.model_name = MODEL_NAME.rsplit(".", maxsplit=1)[0]
        self.buffer_size = buffer_size
        self.threshold = threshold
        self.model = Model(
            wakeword_models=[MODEL_PATH],
            inference_framework=INFERENCE_FRAMEWORK,
        )
        self.stream = None

    def set_stream(self, stream):
        self.stream = stream

    def is_wakeup(self):
        audio_chunk = np.frombuffer(
            self.stream.read(self.buffer_size, exception_on_overflow=False),
            dtype=np.int16,
        )
        audio_chunk = resample(audio_chunk, int(len(audio_chunk) * 16000 / 48000))
        outputs = self.model.predict(audio_chunk, threshold=0.1)
        confidence = outputs[self.model_name]
        print("confidence: ", confidence)
        if confidence > self.threshold:
            print("Wakeword detected!")
            return True
        return False
