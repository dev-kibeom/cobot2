import json
import uuid
from datetime import datetime

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from std_msgs.msg import String
from rcl_interfaces.msg import Log

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', '..'))

from manager_ui.backend.db.connection import SessionLocal
from manager_ui.backend.db.models import CommandLog, ErrorLog, StateLog, ActionLog

_DONE_STATES   = ('IDLE',)
_ERROR_STATES  = ('RECOVERING_FAIL', 'ADMIN_INTERVENTION')
_ACTIVE_STATES = ('EXECUTING', 'RECOVERING_RETRY', 'RECOVERING_RESET')

_LOG_LEVEL = {30: 'WARN', 40: 'ERROR', 50: 'FATAL'}


class DbLoggerNode(Node):
    def __init__(self):
        super().__init__('db_logger_node')

        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.RELIABLE)
        rosout_qos = QoSProfile(
            depth=100,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )

        self.create_subscription(String, '/status',        self._on_status,  qos)
        self.create_subscription(String, '/voice_command', self._on_command, qos)
        self.create_subscription(String, '/stt_result',   self._on_stt,     qos)
        self.create_subscription(Log,    '/rosout',        self._on_rosout,  rosout_qos)

        self._current_command_id: str = ''
        self._pending_raw_text: str   = ''
        self._prev_state: str         = ''
        self._current_step: int       = -1

        self.get_logger().info('DbLoggerNode 시작 — /status, /voice_command, /stt_result, /rosout 구독 중')

    # ── /stt_result 수신 ────────────────────────────
    def _on_stt(self, msg: String):
        self._pending_raw_text = msg.data

    # ── /voice_command 수신 ─────────────────────────
    def _on_command(self, msg: String):
        try:
            sequence = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f'voice_command JSON 파싱 실패: {msg.data}')
            return

        if not isinstance(sequence, list):
            self.get_logger().error('voice_command 형식 오류: JSON 배열이 아님')
            return

        self._current_command_id = str(uuid.uuid4())
        self._current_step = -1

        with SessionLocal() as db:
            db.add(CommandLog(
                command_id=self._current_command_id,
                raw_text=self._pending_raw_text,
                parsed_text=sequence,
                status='received',
            ))
            for seq, step in enumerate(sequence):
                db.add(ActionLog(
                    command_id=self._current_command_id,
                    seq=seq,
                    action=step.get('action', ''),
                    params=step.get('params', {}),
                    status='pending',
                ))
            db.commit()

        self.get_logger().info(
            f'command_log 저장 — id={self._current_command_id[:8]}… '
            f'raw="{self._pending_raw_text[:20]}" actions={len(sequence)}'
        )

    # ── /status 수신 ────────────────────────────────
    def _on_status(self, msg: String):
        try:
            data = json.loads(msg.data)
        except json.JSONDecodeError:
            self.get_logger().error(f'status JSON 파싱 실패: {msg.data}')
            return

        state      = data.get('state', '')
        error_msg  = data.get('error_msg', '')
        command_id = self._current_command_id

        if state == self._prev_state:
            return
        self._prev_state = state

        detail = json.dumps({
            'current_step':   data.get('current_step'),
            'total_steps':    data.get('total_steps'),
            'current_action': data.get('current_action'),
            'error_msg':      error_msg,
        }, ensure_ascii=False)

        step = data.get('current_step')  # 1-indexed

        with SessionLocal() as db:
            db.add(StateLog(command_id=command_id, state=state, detail=detail))

            if command_id:
                cmd = db.query(CommandLog).filter_by(command_id=command_id).first()

                if cmd:
                    if state in _ACTIVE_STATES:
                        cmd.status = 'executing'
                        if step is not None:
                            seq = step - 1
                            if seq != self._current_step:
                                if self._current_step >= 0:
                                    prev = db.query(ActionLog).filter_by(
                                        command_id=command_id, seq=self._current_step
                                    ).first()
                                    if prev:
                                        prev.status = 'done'
                                cur = db.query(ActionLog).filter_by(
                                    command_id=command_id, seq=seq
                                ).first()
                                if cur:
                                    cur.status = 'executing'
                                self._current_step = seq

                    elif state in _DONE_STATES and cmd.status == 'executing':
                        cmd.status = 'done'
                        cmd.finished_at = datetime.now()
                        last = db.query(ActionLog).filter_by(
                            command_id=command_id, seq=self._current_step
                        ).first()
                        if last:
                            last.status = 'done'

                    elif state in _ERROR_STATES:
                        cmd.status = 'failed'
                        cmd.finished_at = datetime.now()
                        cur = db.query(ActionLog).filter_by(
                            command_id=command_id, seq=self._current_step
                        ).first()
                        if cur:
                            cur.status = 'failed'

            db.commit()

        self.get_logger().info(f'state_log 저장 — state={state}')

    # ── /rosout 수신 (WARN 이상만 저장) ─────────────
    def _on_rosout(self, msg: Log):
        if msg.level < 30:  # DEBUG(10), INFO(20) 스킵
            return
        level = _LOG_LEVEL.get(msg.level, 'WARN')
        with SessionLocal() as db:
            db.add(ErrorLog(
                command_id=self._current_command_id or None,
                level=level,
                node_name=msg.name,
                message=msg.msg,
            ))
            db.commit()


def main():
    rclpy.init()
    node = DbLoggerNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
