import re
from mcp_backend.docker_ops import compose_cmd

def test_compose_ps_runs():
    res = compose_cmd("ps")
    assert res.exit_code in (0,1)  # 1 if no services defined
    assert isinstance(res.stdout, str)
