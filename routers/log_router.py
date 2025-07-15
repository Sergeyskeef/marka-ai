
from fastapi import APIRouter, HTTPException

from langchain_api.services.log_parser_service import LogParserService

router = APIRouter(prefix="/logs", tags=["logs"])
log_parser = LogParserService()

@router.get("/recent")
async def get_recent_changes(hours: int = 24) -> list[dict]:
    """Получить список недавних изменений"""
    try:
        return log_parser.get_recent_changes(hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/errors")
async def get_errors(hours: int = 24) -> list[dict]:
    """Получить список ошибок"""
    try:
        return log_parser.get_errors(hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/summary")
async def get_changes_summary(hours: int = 24) -> dict:
    """Получить сводку изменений"""
    try:
        return log_parser.get_changes_summary(hours=hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/files")
async def get_log_files() -> list[str]:
    """Получить список лог-файлов"""
    try:
        return [str(f.name) for f in log_parser.get_log_files()]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
