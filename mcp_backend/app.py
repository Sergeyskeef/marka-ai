from fastapi import FastAPI
from models import ComposeCmdIn, ComposeLogsIn, ContainerExecIn
from docker_ops import compose_cmd, compose_logs, container_exec

app = FastAPI(title="MCP Backend for Server Marka")

@app.post("/compose_cmd")
def api_compose_cmd(body: ComposeCmdIn):
    return compose_cmd(body.cmd, body.service, body.flags, body.project_dir, body.project_name).model_dump()

@app.post("/compose_logs")
def api_compose_logs(body: ComposeLogsIn):
    return compose_logs(
        service=body.service,
        tail=body.tail,
        since=body.since,
        follow=body.follow,
        timestamps=body.timestamps,
        project_dir=body.project_dir,
        project_name=body.project_name
    ).model_dump()

@app.post("/container_exec")
def api_container_exec(body: ContainerExecIn):
    return container_exec(body.service, body.cmd, body.workdir, body.user, body.env, body.timeout, body.tty).model_dump()

@app.get("/health")
def health():
    return {"status": "ok", "service": "mcp-backend"}
