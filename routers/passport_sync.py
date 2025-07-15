
from fastapi import APIRouter, HTTPException

from langchain_api.globals import passport_sync_service

router = APIRouter(prefix="/passport/sync", tags=["passport"])

def check_service():
    """Проверяет инициализацию сервиса"""
    if passport_sync_service is None:
        raise HTTPException(
            status_code=503,
            detail="PassportSyncService не инициализирован"
        )

@router.get("/status")
async def get_sync_status() -> dict:
    """Получить статус автосинхронизации"""
    check_service()
    try:
        return {
            "enabled": passport_sync_service.is_enabled(),
            "last_sync": passport_sync_service.get_last_sync_time(),
            "pending_changes": passport_sync_service.get_pending_changes_count()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/apply")
async def apply_changes() -> dict:
    """Применить накопленные изменения"""
    check_service()
    try:
        result = passport_sync_service.apply_changes()
        return {
            "success": True,
            "changes_applied": result["changes_applied"],
            "timestamp": result["timestamp"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/changes")
async def get_changes() -> list[dict]:
    """Получить список накопленных изменений"""
    check_service()
    try:
        changes = passport_sync_service.get_pending_changes()
        # Преобразуем ChangeReport в словарь
        return [{"changes": change.changes} for change in changes]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/changes")
async def clear_changes() -> dict:
    """Очистить накопленные изменения"""
    check_service()
    try:
        passport_sync_service.clear_changes()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
