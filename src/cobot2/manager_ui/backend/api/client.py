from fastapi import APIRouter
from manager_ui.backend.services.state_service import get_current_state

router = APIRouter(prefix='/client', tags=['client'])


@router.get('/status')
def get_status():
    return get_current_state()
