import os
from pydantic import BaseModel


class Settings(BaseModel):
	app_name: str = "mark-mcp"
	bearer_token: str = os.getenv("MCP_TOKEN", "change-me")
	graphiti_url: str = os.getenv("GRAPHITI_URL", "http://graphiti:7878").rstrip("/")
	allow_paths: list[str] = os.getenv("ALLOW_PATHS", "/srv/mark,/var/log/mark,/data/mark").split(",")
	log_file: str = os.getenv("LOG_FILE", "/var/log/mark/mark-mcp.log")
	max_read_bytes: int = int(os.getenv("MCP_MAX_READ_BYTES", "1048576"))
	max_glob_items: int = int(os.getenv("MCP_MAX_GLOB_ITEMS", "500"))
	request_timeout_s: int = int(os.getenv("MCP_REQUEST_TIMEOUT", "20"))
	host: str = os.getenv("HOST", "0.0.0.0")
	port: int = int(os.getenv("PORT", "8788"))
	env: str = os.getenv("ENV", "dev")
	dry_run_default: bool = os.getenv("DRY_RUN_DEFAULT", "true").lower() == "true"
	# OAuth
	oauth_enabled: bool = os.getenv("OAUTH_ENABLED", "false").lower() == "true"
	oauth_issuer: str | None = os.getenv("OAUTH_ISSUER")  # e.g., https://auth.example.com/realms/marka
	oauth_resource: str | None = os.getenv("OAUTH_RESOURCE")  # e.g., https://<DOMAIN>/mcp/


settings = Settings()
