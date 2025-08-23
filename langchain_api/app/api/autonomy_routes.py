"""
Autonomy API routes (stubs)
"""
from fastapi import APIRouter

router = APIRouter()

@router.post("/autonomy/start_project")
async def start_project():
	return {"status": "started"}

@router.post("/autonomy/execute_task")
async def execute_task():
	return {"status": "queued"}

@router.get("/autonomy/status")
async def status():
	return {"status": "idle"}

@router.post("/autonomy/stop")
async def stop():
	return {"status": "stopped"}

@router.post("/autonomy/set_autonomy_level/{level}")
async def set_level(level: int):
	return {"status": "ok", "level": level}

@router.get("/autonomy/capabilities")
async def capabilities():
	return {"capabilities": ["plan", "code", "test", "document"]}