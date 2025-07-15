import time
import httpx
import pytest

@pytest.fixture(scope="session", autouse=True)
def wait_graphiti():
    url = "http://graphiti:7878/health"
    for _ in range(30):  # 30 × 2 s = 1 мин
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.TransportError:
            pass
        time.sleep(2)
    pytest.exit("Graphiti did not become healthy in time", returncode=1) 