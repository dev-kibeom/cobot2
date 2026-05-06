from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, Float, Boolean, DateTime, JSON
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class CommandLog(Base):
    __tablename__ = 'command_logs'

    command_id  = Column(String(100), primary_key=True)
    raw_text    = Column(Text)
    parsed_text = Column(JSON)
    status      = Column(String(50))
    created_at  = Column(DateTime, default=datetime.now)
    finished_at = Column(DateTime)


class ErrorLog(Base):
    __tablename__ = 'error_logs'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    command_id = Column(String(100))
    level      = Column(String(10))
    node_name  = Column(String(100))
    message    = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class StateLog(Base):
    __tablename__ = 'state_logs'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    command_id = Column(String(100))
    state      = Column(String(50))
    detail     = Column(Text)
    created_at = Column(DateTime, default=datetime.now)


class ActionLog(Base):
    __tablename__ = 'action_logs'

    id         = Column(Integer, primary_key=True, autoincrement=True)
    command_id = Column(String(100))
    seq        = Column(Integer)
    action     = Column(String(100))
    params     = Column(JSON)
    status     = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)


class DetectionLog(Base):
    __tablename__ = 'detection_logs'

    id          = Column(Integer, primary_key=True, autoincrement=True)
    command_id  = Column(String(100))
    object_name = Column(String(100))
    confidence  = Column(Float)
    position_x  = Column(Float)
    position_y  = Column(Float)
    position_z  = Column(Float)
    detected    = Column(Boolean)
    created_at  = Column(DateTime, default=datetime.now)
