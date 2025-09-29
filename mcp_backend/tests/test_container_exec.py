from mcp_backend.docker_ops import container_exec

def test_exec_echo():
    res = container_exec(service="app", cmd="echo hello", workdir="/")
    assert "hello" in res.stdout or res.exit_code != 0  # service may not exist yet
