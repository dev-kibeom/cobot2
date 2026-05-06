from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc
from manager_ui.backend.db.connection import get_db
from manager_ui.backend.db.models import ErrorLog, CommandLog, ActionLog

router = APIRouter(prefix='/admin', tags=['admin'])

# ── 규칙 기반 분석 ──────────────────────────────────
_RULES = [
    (['velocity', 'speed', 'overspeed'],
     "속도 초과 — '{action}' 액션의 이동 속도 또는 가속도 파라미터를 줄여보세요."),
    (['joint', 'limit', 'range'],
     "조인트 한계 도달 — '{action}' 목표 좌표가 로봇 작동 범위를 벗어났습니다. 좌표를 조정하거나 자세 계획을 확인하세요."),
    (['timeout', 'timed out', 'no response'],
     "타임아웃 — 로봇 컨트롤러 연결 지연 또는 동작 완료 대기 시간 초과입니다. 통신 상태와 대기 시간 설정을 확인하세요."),
    (['collision', 'contact', 'force'],
     "충돌/접촉 감지 — '{action}' 실행 중 장애물과 접촉이 감지되었습니다. 작업 공간을 정리하고 경로를 재확인하세요."),
    (['detection', 'yolo', 'confidence', 'not found'],
     "객체 탐지 실패 — '{action}' 대상 객체를 찾지 못했습니다. 카메라 시야, 조명, 객체 위치를 확인하세요."),
    (['depth', 'realsense', 'frame'],
     "카메라 센서 오류 — RealSense 스트림이 중단되었습니다. 카메라 연결 및 드라이버 상태를 확인하세요."),
    (['gripper', 'grasp', 'pick'],
     "그리퍼 동작 오류 — '{action}' 중 파지에 실패했습니다. 객체 크기·위치와 그리퍼 설정을 확인하세요."),
    (['memory', 'malloc', 'segfault'],
     "시스템 오류 — 메모리 관련 오류가 발생했습니다. 노드를 재시작하고 시스템 자원을 확인하세요."),
]

def _make_recommendation(message: str, action: str) -> str:
    msg_lower = message.lower()
    for keywords, template in _RULES:
        if any(kw in msg_lower for kw in keywords):
            return template.format(action=action or '해당 동작')
    return f"'{action or '알 수 없는 동작'}' 실행 중 오류가 발생했습니다. '{message[:60]}' 로그를 참고해 해당 노드 상태를 점검하세요."


def _severity_order(level: str) -> int:
    return {'FATAL': 0, 'ERROR': 1, 'WARN': 2}.get(level, 3)


@router.get('/recommendations')
def get_recommendations(limit: int = Query(30, le=100), db: Session = Depends(get_db)):
    errors = (
        db.query(ErrorLog)
        .order_by(desc(ErrorLog.created_at))
        .limit(limit)
        .all()
    )

    results = []
    for err in errors:
        command = None
        action  = None

        if err.command_id:
            command = db.query(CommandLog).filter_by(command_id=err.command_id).first()
            # 에러 발생 시점에 executing 또는 failed 상태인 액션 우선
            action = (
                db.query(ActionLog)
                .filter_by(command_id=err.command_id)
                .filter(ActionLog.status.in_(['executing', 'failed']))
                .order_by(ActionLog.seq)
                .first()
            ) or (
                db.query(ActionLog)
                .filter_by(command_id=err.command_id)
                .order_by(desc(ActionLog.seq))
                .first()
            )

        action_name = action.action if action else None
        rec = _make_recommendation(err.message or '', action_name or '')

        results.append({
            'id':               err.id,
            'level':            err.level,
            'node_name':        err.node_name,
            'error_message':    err.message,
            'command_id':       err.command_id,
            'command_text':     command.raw_text if command else None,
            'action_at_error':  action_name,
            'recommendation':   rec,
            'created_at':       err.created_at,
        })

    # FATAL/ERROR 먼저, 그 다음 WARN
    results.sort(key=lambda x: _severity_order(x['level'] or ''))
    return results
