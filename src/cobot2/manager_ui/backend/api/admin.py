from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc
from manager_ui.backend.db.connection import get_db
from manager_ui.backend.db.models import CommandLog, ErrorLog, StateLog, ActionLog, DetectionLog
from manager_ui.backend.services.video_service import video_service

router = APIRouter(prefix='/admin', tags=['admin'])


@router.get('/commands')
def get_commands(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    rows = db.query(CommandLog).order_by(desc(CommandLog.created_at)).limit(limit).all()
    return [
        {
            'command_id':  r.command_id,
            'raw_text':    r.raw_text,
            'parsed_text': r.parsed_text,
            'status':      r.status,
            'created_at':  r.created_at,
            'finished_at': r.finished_at,
        }
        for r in rows
    ]


@router.get('/errors')
def get_errors(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = db.query(ErrorLog).order_by(desc(ErrorLog.created_at)).limit(limit).all()
    return [
        {
            'id':         r.id,
            'command_id': r.command_id,
            'level':      r.level,
            'node_name':  r.node_name,
            'message':    r.message,
            'created_at': r.created_at,
        }
        for r in rows
    ]


@router.get('/states')
def get_states(limit: int = Query(100, le=500), db: Session = Depends(get_db)):
    rows = db.query(StateLog).order_by(desc(StateLog.created_at)).limit(limit).all()
    return [
        {
            'id':         r.id,
            'command_id': r.command_id,
            'state':      r.state,
            'detail':     r.detail,
            'created_at': r.created_at,
        }
        for r in rows
    ]


@router.get('/detections')
def get_detections(limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    rows = db.query(DetectionLog).order_by(desc(DetectionLog.created_at)).limit(limit).all()
    return [
        {
            'id':          r.id,
            'command_id':  r.command_id,
            'object_name': r.object_name,
            'confidence':  r.confidence,
            'position_x':  r.position_x,
            'position_y':  r.position_y,
            'position_z':  r.position_z,
            'detected':    r.detected,
            'created_at':  r.created_at,
        }
        for r in rows
    ]


@router.get('/actions')
def get_actions(command_id: str = Query(None), limit: int = Query(50, le=200), db: Session = Depends(get_db)):
    q = db.query(ActionLog)
    if command_id:
        q = q.filter(ActionLog.command_id == command_id)
    rows = q.order_by(desc(ActionLog.created_at), ActionLog.seq).limit(limit).all()
    return [
        {
            'id':         r.id,
            'command_id': r.command_id,
            'seq':        r.seq,
            'action':     r.action,
            'params':     r.params,
            'status':     r.status,
            'created_at': r.created_at,
        }
        for r in rows
    ]


@router.get('/detection/video')
def detection_video():
    if not video_service.is_running():
        try:
            video_service.start()
        except RuntimeError as e:
            from fastapi import HTTPException
            raise HTTPException(status_code=503, detail=str(e))
    return StreamingResponse(
        video_service.mjpeg_stream(),
        media_type='multipart/x-mixed-replace; boundary=frame',
    )


@router.get('/detection/video/status')
def detection_video_status():
    return {'running': video_service.is_running()}
