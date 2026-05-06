_state = {
    'robot_state':  'IDLE',
    'wake_word':    'hello rokey',
    'confidence':   0.0,
    'wakeup_detected': False,
    'stt_text':     '',
    'message':      '명령을 듣고 있습니다.',
}


def get_current_state() -> dict:
    return dict(_state)


def update_robot_state(state: str, message: str = ''):
    _state['robot_state'] = state
    if message:
        _state['message'] = message


def update_wakeup(wake_word: str, confidence: float, detected: bool):
    _state['wake_word']        = wake_word
    _state['confidence']       = confidence
    _state['wakeup_detected']  = detected


def update_stt(text: str):
    _state['stt_text'] = text
