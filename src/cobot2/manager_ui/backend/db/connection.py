from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from manager_ui.backend.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def check_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        return True
    except Exception as e:
        print(f'DB 연결 실패: {e}')
        return False
