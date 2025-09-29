from mcp_backend.docker_ops import compose_logs

def test_compose_logs():
    res = compose_logs(service="app", tail=10)
    assert isinstance(res.stdout, str)
    assert res.exit_code in (0, 1)  # service may not exist
