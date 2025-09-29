import asyncio
import json
import logging
import os
from typing import Any

from fastapi import Depends, FastAPI, Header, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse

from mark_mcp.logging_config import setup_logging
from mark_mcp.security import require_auth, require_scope_write
from mark_mcp.config import settings
from mark_mcp.fs_tools import fs_glob, fs_read, fs_write
from mark_mcp.memory_tools import memory_search, memory_upsert
from mark_mcp.agent_tools import agent_run_task
from mark_mcp.repo_tools import repo_snapshot, git_local_commit
from mark_mcp.docker_tools import compose_cmd, compose_logs, container_exec, tests_run
from mark_mcp.mcp_server import mcp

setup_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name, redirect_slashes=False)

# Mount MCP SSE/JSON-RPC app at /mcp (handled by mcp SDK)
# Use include_in_schema=False to prevent automatic redirects
app.mount("/mcp", mcp.sse_app(), name="mcp")

# Add explicit handlers for /mcp endpoint to handle discovery and JSON-RPC
@app.get("/mcp")
async def mcp_discovery():
    """MCP discovery endpoint"""
    return {
        "protocol": "mcp",
        "version": "2025-06-18",
        "capabilities": {
            "tools": True,
            "resources": True,
            "prompts": False
        },
        "serverInfo": {
            "name": "markmind-mcp",
            "version": "1.0.0"
        }
    }

@app.post("/mcp")
async def mcp_jsonrpc(request: Request):
    """MCP JSON-RPC endpoint"""
    try:
        body = await request.body()
        data = json.loads(body)
        
        # Handle initialize request
        if data.get("method") == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {
                        "tools": {},
                        "resources": {
                            "subscribe": True
                        }
                    },
                    "serverInfo": {
                        "name": "markmind-mcp",
                        "version": "1.0.0"
                    }
                }
            }
        
        # Handle tools/list request
        elif data.get("method") == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {
                    "tools": [
                        {
                            "name": "search",
                            "description": "Search through memory and files for information",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {
                                        "type": "string",
                                        "description": "Search query"
                                    },
                                    "limit": {
                                        "type": "integer",
                                        "description": "Maximum number of results",
                                        "default": 10
                                    }
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "fetch",
                            "description": "Fetch document content by ID",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "id": {
                                        "type": "string",
                                        "description": "Document ID to fetch"
                                    }
                                },
                                "required": ["id"]
                            }
                        },
                        {
                            "name": "fs_glob",
                            "description": "Search files by pattern",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "pattern": {"type": "string", "description": "File pattern to search"},
                                    "cwd": {"type": "string", "description": "Working directory", "default": "/home/sergey/marka"}
                                },
                                "required": ["pattern"],
                                "additionalProperties": False
                            }
                        },
                        {
                            "name": "fs_read",
                            "description": "Read file contents",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "max_bytes": {"type": "integer"}
                                },
                                "required": ["path"]
                            }
                        },
                        {
                            "name": "fs_write",
                            "description": "Write file contents",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                    "mode": {"type": "string", "default": "w"}
                                },
                                "required": ["path", "content"]
                            }
                        },
                        {
                            "name": "memory_search",
                            "description": "Search memory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "query": {"type": "string"},
                                    "limit": {"type": "integer", "default": 10}
                                },
                                "required": ["query"]
                            }
                        },
                        {
                            "name": "compose_cmd",
                            "description": "Run docker-compose commands",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "cmd": {"type": "string", "default": "ps"},
                                    "service": {"type": "string"},
                                    "flags": {"type": "string"}
                                },
                                "required": ["cmd"]
                            }
                        },
                        {
                            "name": "compose_logs",
                            "description": "Get container logs",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "service": {"type": "string"},
                                    "tail": {"type": "integer", "default": 200},
                                    "since": {"type": "string"}
                                },
                                "required": ["service"]
                            }
                        },
                        {
                            "name": "container_exec",
                            "description": "Execute commands in containers",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "service": {"type": "string"},
                                    "cmd": {"type": "string"},
                                    "workdir": {"type": "string", "default": "/srv/mark"},
                                    "timeout": {"type": "integer", "default": 300}
                                },
                                "required": ["service", "cmd"]
                            }
                        },
                        {
                            "name": "tests_run",
                            "description": "Run tests",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "service": {"type": "string"},
                                    "cmd": {"type": "string", "default": "pytest -q"},
                                    "report_out": {"type": "string", "default": "/data/mark/reports"}
                                },
                                "required": ["service"]
                            }
                        },
                        {
                            "name": "repo_snapshot",
                            "description": "Create repository snapshot",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "label": {"type": "string"}
                                }
                            }
                        },
                        {
                            "name": "git_local_commit",
                            "description": "Make git commit",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "message": {"type": "string"}
                                },
                                "required": ["message"]
                            }
                        },
                        {
                            "name": "memory_upsert",
                            "description": "Store information in memory",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {"type": "string"},
                                    "metadata": {"type": "object"}
                                },
                                "required": ["text"]
                            }
                        },
                        {
                            "name": "agent_run_task",
                            "description": "Run agent tasks",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "task": {"type": "string"},
                                    "params": {"type": "object"},
                                    "dry_run": {"type": "boolean"}
                                },
                                "required": ["task"]
                            }
                        }
                    ]
                }
            }
        
        # Handle resources/list request
        elif data.get("method") == "resources/list":
            return {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "result": {
                    "resources": [
                        {
                            "uri": "file:///home/sergey/marka",
                            "name": "Project Root",
                            "description": "Root directory of the mark project - full access to all files and directories",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/docs",
                            "name": "Documentation",
                            "description": "Project documentation directory",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/logs",
                            "name": "Logs",
                            "description": "Application logs directory",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/data",
                            "name": "Data",
                            "description": "Application data directory",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/langchain_api",
                            "name": "LangChain API",
                            "description": "LangChain API service directory",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/mark_mcp",
                            "name": "MCP Server",
                            "description": "MCP server source code",
                            "mimeType": "application/x-directory"
                        },
                        {
                            "uri": "file:///home/sergey/marka/cursor_memory",
                            "name": "Cursor Memory",
                            "description": "Cursor AI memory storage",
                            "mimeType": "application/x-directory"
                        }
                    ]
                }
            }
        
        # Handle resources/read request
        elif data.get("method") == "resources/read":
            uri = data.get("params", {}).get("uri", "")
            if uri.startswith("file:///home/sergey/marka"):
                # Convert URI to file path
                file_path = uri.replace("file://", "")
                
                try:
                    if os.path.isdir(file_path):
                        # List directory contents
                        files = os.listdir(file_path)
                        contents = []
                        for file in files[:20]:  # Limit to first 20 files
                            file_full_path = os.path.join(file_path, file)
                            if os.path.isdir(file_full_path):
                                contents.append(f"📁 {file}/")
                            else:
                                size = os.path.getsize(file_full_path)
                                contents.append(f"📄 {file} ({size} bytes)")
                        
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "result": {
                                "contents": [
                                    {
                                        "uri": uri,
                                        "mimeType": "application/x-directory",
                                        "text": f"Directory: {uri}\n\nContents:\n" + "\n".join(contents)
                                    }
                                ]
                            }
                        }
                    elif os.path.isfile(file_path):
                        # Read file content (limit to first 10KB)
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read(10240)
                            if len(content) == 10240:
                                content += "\n... (truncated)"
                        
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "result": {
                                "contents": [
                                    {
                                        "uri": uri,
                                        "mimeType": "text/plain",
                                        "text": content
                                    }
                                ]
                            }
                        }
                    else:
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "error": {
                                "code": -32602,
                                "message": f"Path not found: {uri}"
                            }
                        }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error reading resource: {str(e)}"
                        }
                    }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {
                        "code": -32602,
                        "message": "Invalid URI"
                    }
                }
        
        # Handle tools/call request
        elif data.get("method") == "tools/call":
            tool_name = data.get("params", {}).get("name")
            arguments = data.get("params", {}).get("arguments", {})
            
            if tool_name == "search":
                query = arguments.get("query", "")
                limit = arguments.get("limit", 10)
                # Имитируем поиск по файлам проекта
                import os
                results = []
                try:
                    for root, dirs, files in os.walk("/srv/mark"):
                        for file in files:
                            file_path = os.path.join(root, file)
                            # Search in filename
                            if query.lower() in file.lower():
                                results.append({
                                    "id": file_path,
                                    "title": file,
                                    "text": f"File found: {file_path}",
                                    "url": f"file://{file_path}"
                                })
                            # Search in file content (for text files)
                            elif file.endswith(('.txt', '.md', '.py', '.js', '.json', '.yml', '.yaml')):
                                try:
                                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                        content = f.read(1000)  # Read first 1000 chars
                                        if query.lower() in content.lower():
                                            results.append({
                                                "id": file_path,
                                                "title": file,
                                                "text": f"Content found in: {file_path}",
                                                "url": f"file://{file_path}"
                                            })
                                except:
                                    pass  # Skip files that can't be read
                            
                            if len(results) >= limit:
                                break
                        if len(results) >= limit:
                            break
                except:
                    results = [{"id": "demo", "title": "Demo file", "text": f"Search for '{query}'", "url": "file://demo"}]
                
                return {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Search results for '{query}': Found {len(results)} results in project files."
                            }
                        ]
                    }
                }
            
            elif tool_name == "fetch":
                doc_id = arguments.get("id", "")
                try:
                    if doc_id == "demo":
                        content = "This is a demo file content for testing MCP server."
                    else:
                        # Попытка прочитать реальный файл
                        import os
                        if os.path.exists(doc_id) and doc_id.startswith("/srv/mark"):
                            with open(doc_id, 'r', encoding='utf-8', errors='ignore') as f:
                                content = f.read()[:10000]  # Ограничиваем размер
                        else:
                            content = f"File content for {doc_id} (demo)"
                    
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": content
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error reading file: {str(e)}"
                        }
                    }
            
            elif tool_name == "fs_glob":
                pattern = arguments.get("pattern", "")
                cwd = arguments.get("cwd", "/home/sergey/marka")
                dot = arguments.get("dot", False)
                limit = arguments.get("limit", 1000)
                
                import glob
                import os
                from pathlib import Path
                import urllib.parse
                
                try:
                    def to_local_path(path_str):
                        """Convert file:// URI to local path"""
                        if path_str.startswith("file://"):
                            return urllib.parse.urlparse(path_str).path
                        return path_str
                    
                    def normalize_glob_args(pattern, cwd):
                        """Normalize glob arguments for reliable file searching"""
                        # Convert file:// URIs to local paths
                        cwd = to_local_path(cwd) if cwd else os.getcwd()
                        pattern = to_local_path(pattern)
                        
                        # Handle absolute patterns
                        if os.path.isabs(pattern):
                            base_dir = os.path.dirname(pattern)
                            rel_pattern = os.path.basename(pattern)
                            return rel_pattern, base_dir
                        
                        # Relative pattern with cwd
                        return pattern, cwd
                    
                    # Normalize arguments
                    rel_pattern, base_dir = normalize_glob_args(pattern, cwd)
                    
                    # Use pathlib for more reliable globbing
                    base_path = Path(base_dir)
                    if not base_path.exists():
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "error": {
                                "code": -32602,
                                "message": f"Directory not found: {base_dir}"
                            }
                        }
                    
                    # Perform glob search
                    if dot:
                        # Include hidden files
                        files = list(base_path.glob(rel_pattern))
                    else:
                        # Exclude hidden files (default)
                        files = [f for f in base_path.glob(rel_pattern) if not f.name.startswith('.')]
                    
                    # Limit results and convert to absolute paths
                    results = []
                    for f in files[:limit]:
                        abs_path = str(f.resolve())
                        results.append({
                            "path": abs_path,
                            "uri": f"file://{abs_path}",
                            "type": "file" if f.is_file() else "directory",
                            "size": f.stat().st_size if f.is_file() else 0
                        })
                    
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Found {len(results)} files matching '{pattern}' in '{base_dir}':\n" + 
                                           "\n".join([f"{r['type']}: {r['path']}" for r in results])
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error in fs_glob: {str(e)}"
                        }
                    }
            
            elif tool_name == "fs_read":
                path = arguments.get("path", "")
                encoding = arguments.get("encoding", "utf-8")
                max_bytes = arguments.get("maxBytes", 10240)
                
                import os
                import urllib.parse
                
                try:
                    def to_local_path(path_str):
                        """Convert file:// URI to local path"""
                        if path_str.startswith("file://"):
                            return urllib.parse.urlparse(path_str).path
                        return path_str
                    
                    # Normalize path
                    local_path = to_local_path(path)
                    
                    # Security check: ensure path is within allowed directories
                    allowed_dirs = ["/home/sergey/marka", "/workspace", "/srv/mark"]
                    # Normalize path for comparison
                    normalized_path = os.path.abspath(local_path)
                    if not any(normalized_path.startswith(allowed_dir) for allowed_dir in allowed_dirs):
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "error": {
                                "code": -32602,
                                "message": f"Access denied: path outside allowed directories"
                            }
                        }
                    
                    if not os.path.exists(local_path):
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "error": {
                                "code": -32602,
                                "message": f"File not found: {local_path}"
                            }
                        }
                    
                    if not os.path.isfile(local_path):
                        return {
                            "jsonrpc": "2.0",
                            "id": data.get("id"),
                            "error": {
                                "code": -32602,
                                "message": f"Path is not a file: {local_path}"
                            }
                        }
                    
                    # Read file with size limit
                    file_size = os.path.getsize(local_path)
                    read_size = min(max_bytes, file_size)
                    
                    with open(local_path, 'r', encoding=encoding, errors='ignore') as f:
                        content = f.read(read_size)
                        truncated = read_size < file_size
                    
                    result_text = content
                    if truncated:
                        result_text += f"\n... (truncated, showing {read_size}/{file_size} bytes)"
                    
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": result_text
                                }
                            ],
                            "metadata": {
                                "path": local_path,
                                "uri": f"file://{local_path}",
                                "size": file_size,
                                "read": read_size,
                                "truncated": truncated,
                                "encoding": encoding
                            }
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error reading file: {str(e)}"
                        }
                    }
            
            elif tool_name == "fs_write":
                path = arguments.get("path", "")
                content = arguments.get("content", "")
                encoding = arguments.get("encoding", "utf-8")
                import os
                try:
                    # Создаем директорию если нужно
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    with open(path, 'w', encoding=encoding) as f:
                        f.write(content)
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Successfully wrote {len(content)} characters to {path}"
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error writing file: {str(e)}"
                        }
                    }
            
            elif tool_name == "compose_cmd":
                cmd = arguments.get("cmd", "")
                service = arguments.get("service")
                flags = arguments.get("flags")
                try:
                    from mark_mcp.docker_tools import compose_cmd
                    result = await compose_cmd(cmd, service, flags)
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Compose command '{cmd}' executed:\n{result.get('stdout', '')}\nExit code: {result.get('rc', result.get('exit_code', 0))}"
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error executing compose command: {str(e)}"
                        }
                    }
            
            elif tool_name == "compose_logs":
                service = arguments.get("service", "")
                tail = arguments.get("tail", 200)
                since = arguments.get("since")
                try:
                    from mark_mcp.docker_tools import compose_logs
                    result = await compose_logs(service, tail, since)
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Logs for service '{service}':\n{result.get('logs', result.get('stdout', ''))}"
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error getting logs: {str(e)}"
                        }
                    }
            
            elif tool_name == "container_exec":
                service = arguments.get("service", "")
                cmd = arguments.get("cmd", "")
                workdir = arguments.get("workdir", "/srv/mark")
                timeout = arguments.get("timeout", 300)
                try:
                    from mark_mcp.docker_tools import container_exec
                    result = await container_exec(service, cmd, workdir, timeout)
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "result": {
                            "content": [
                                {
                                    "type": "text",
                                    "text": f"Command executed in '{service}':\n{result.get('output', result.get('stdout', ''))}\nExit code: {result.get('exit_code', 0)}"
                                }
                            ]
                        }
                    }
                except Exception as e:
                    return {
                        "jsonrpc": "2.0",
                        "id": data.get("id"),
                        "error": {
                            "code": -32603,
                            "message": f"Error executing command: {str(e)}"
                        }
                    }
            
            # Для остальных инструментов возвращаем заглушку
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": f"Tool '{tool_name}' called with arguments: {arguments}. This is a placeholder implementation."
                            }
                        ]
                    }
                }
        
        # Handle notifications/initialized
        elif data.get("method") == "notifications/initialized":
            return {"jsonrpc": "2.0", "result": None}
        
        # Handle other requests
        else:
            return {
                "jsonrpc": "2.0",
                "id": data.get("id"),
                "error": {
                    "code": -32601,
                    "message": "Method not found"
                }
            }
            
    except Exception as e:
        return {
            "jsonrpc": "2.0",
            "id": data.get("id") if 'data' in locals() else None,
            "error": {
                "code": -32603,
                "message": "Internal error",
                "data": str(e)
            }
        }


@app.get("/.well-known/oauth-protected-resource")
async def oauth_metadata() -> dict[str, Any]:
	issuer = settings.oauth_issuer or "https://<AUTH_DOMAIN>/realms/marka"
	resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")
	return {
		"resource": resource,
		"authorization_servers": [issuer],
		"scopes_supported": ["mcp.read", "mcp.write"],
	}


@app.get("/.well-known/oauth-protected-resource/{suffix:path}")
async def oauth_metadata_suffix(suffix: str) -> dict[str, Any]:
	# return the same metadata for any suffix (e.g., /mcp)
	return await oauth_metadata()


@app.middleware("http")
async def audit_log(request: Request, call_next):
    try:
        body = await request.body()
        logger.info(f"MCP CALL {request.method} {request.url.path} q={dict(request.query_params)} body={body[:500]!r}")
        response = await call_next(request)
        logger.info(f"MCP RESP {request.method} {request.url.path} status={response.status_code}")
        return response
    except HTTPException as e:
        # Convert HTTPException into a response to avoid TaskGroup bubbling → 500
        logger.info(f"MCP HTTP {request.method} {request.url.path} status={e.status_code} detail={e.detail}")
        return JSONResponse({"detail": e.detail}, status_code=e.status_code, headers=e.headers or {})
    except Exception as e:
        logger.exception(f"MCP ERROR {request.method} {request.url.path}: {e}")
        return JSONResponse({"detail": "Internal Server Error"}, status_code=500)


@app.middleware("http")
async def auth_guard(request: Request, call_next):
    # Enforce OAuth on MCP transport paths, but allow unauthenticated access for discovery
    if (request.url.path == "/mcp" or request.url.path.startswith("/mcp/") or 
        request.url.path == "/tools" or request.url.path.startswith("/tools/") or
        request.url.path == "/mcp/tools"):
        authorization = request.headers.get("authorization")
        
        # Debug logging
        logger.info(f"Auth check: path={request.url.path}, method={request.method}, has_auth={bool(authorization)}")
        
        # Allow GET and POST requests without auth for discovery and JSON-RPC
        if request.method in ["GET", "POST"] and (not authorization or not authorization.startswith("Bearer ")):
            logger.info(f"Allowing unauthenticated {request.method} request to {request.url.path}")
            return await call_next(request)
        # For other methods, require auth
        if not authorization or not authorization.startswith("Bearer "):
            resource = (settings.oauth_resource or "https://<DOMAIN>/mcp").rstrip("/")
            logger.info(f"Blocking request to {request.url.path}: missing bearer token")
            return JSONResponse(
                {"detail": "Missing bearer token"},
                status_code=401,
                headers={
                    "WWW-Authenticate": f'Bearer authorization_uri="/.well-known/oauth-protected-resource", resource="{resource}"'
                },
            )
        # Otherwise validate and map scopes; convert exceptions into responses
        try:
            await require_auth(authorization=authorization, request=request)
        except HTTPException as e:
            return JSONResponse({"detail": e.detail}, status_code=e.status_code, headers=e.headers)
    return await call_next(request)


@app.get("/health")
async def health() -> dict[str, Any]:
	return {"status": "ok", "service": settings.app_name}


@app.get("/tools")
async def list_tools() -> dict:
	return {
		"tools": [
			{"name": "fs_glob", "params": ["pattern", "root?" ]},
			{"name": "fs_read", "params": ["path", "max_bytes?"]},
			{"name": "fs_write", "params": ["path", "content", "mode?"]},
			{"name": "repo_snapshot", "params": ["label?"]},
			{"name": "git_local_commit", "params": ["message"]},
			{"name": "compose_cmd", "params": ["cmd", "service?", "flags?"]},
			{"name": "compose_logs", "params": ["service", "tail?", "since?"]},
			{"name": "container_exec", "params": ["service", "cmd", "workdir?", "timeout?"]},
			{"name": "tests_run", "params": ["service", "cmd?", "report_out?"]},
			{"name": "memory_search", "params": ["query", "limit?"]},
			{"name": "search", "params": ["query", "limit?"]},
			{"name": "memory_upsert", "params": ["text", "metadata?"]},
			{"name": "agent_run_task", "params": ["task", "params?", "dry_run?"]},
		]
	}

@app.get("/mcp/tools")
async def list_mcp_tools() -> dict:
    """MCP tools endpoint for ChatGPT compatibility"""
    return {
        "tools": [
            {"name": "fs_glob", "params": ["pattern", "root?" ]},
            {"name": "fs_read", "params": ["path", "max_bytes?"]},
            {"name": "fs_write", "params": ["path", "content", "mode?"]},
            {"name": "repo_snapshot", "params": ["label?"]},
            {"name": "git_local_commit", "params": ["message"]},
            {"name": "compose_cmd", "params": ["cmd", "service?", "flags?"]},
            {"name": "compose_logs", "params": ["service", "tail?", "since?"]},
            {"name": "container_exec", "params": ["service", "cmd", "workdir?", "timeout?"]},
            {"name": "tests_run", "params": ["service", "cmd?", "report_out?"]},
            {"name": "memory_search", "params": ["query", "limit?"]},
            {"name": "search", "params": ["query", "limit?"]},
            {"name": "memory_upsert", "params": ["text", "metadata?"]},
            {"name": "agent_run_task", "params": ["task", "params?", "dry_run?"]},
        ]
    }

@app.post("/tools/{tool_name}")
async def call_tool_via_http(tool_name: str, payload: dict, request: Request):
    """HTTP endpoint to call MCP tools - for ChatGPT api_tool bridge"""
    try:
        # Create a mock JSON-RPC request
        class MockRequest:
            async def body(self):
                return json.dumps({
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": payload
                    },
                    "id": 1
                }).encode()
        
        mock_request = MockRequest()
        
        # Call the MCP handler
        response = await mcp_jsonrpc(mock_request)
        
        # Extract result from JSON-RPC response
        if "result" in response:
            return response["result"]
        elif "error" in response:
            return {"error": response["error"]}
        else:
            return response
            
    except Exception as e:
        return {"error": {"message": str(e)}}

@app.get("/resources")
async def list_resources_http():
    """HTTP endpoint to list resources - for ChatGPT api_tool bridge"""
    try:
        # Create a mock JSON-RPC request
        class MockRequest:
            async def body(self):
                return json.dumps({
                    "jsonrpc": "2.0",
                    "method": "resources/list",
                    "id": 1
                }).encode()
        
        mock_request = MockRequest()
        
        # Call the MCP handler
        response = await mcp_jsonrpc(mock_request)
        
        # Extract result from JSON-RPC response
        if "result" in response:
            return response["result"]
        elif "error" in response:
            return {"error": response["error"]}
        else:
            return response
            
    except Exception as e:
        return {"error": {"message": str(e)}}


@app.get("/tools/fs_glob")
async def tool_fs_glob(pattern: str, root: str | None = None, _: None = Depends(require_auth)) -> dict:
	items = await fs_glob(pattern, root)
	return {"items": items}


@app.get("/tools/fs_read")
async def tool_fs_read(path: str, max_bytes: int | None = None, _: None = Depends(require_auth)) -> dict:
	content = await fs_read(path, max_bytes)
	return {"path": path, "content": content}


@app.post("/tools/fs_write")
async def tool_fs_write(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	require_scope_write(request)
	path = payload.get("path")
	content = payload.get("content", "")
	mode = payload.get("mode", "w")
	return await fs_write(path, content, mode)


@app.post("/tools/repo_snapshot")
async def tool_repo_snapshot(payload: dict | None = None, request: Request = None, _: None = Depends(require_auth)) -> dict:
	# считаем записью — требует mcp.write
	if request is not None:
		require_scope_write(request)
	label = (payload or {}).get("label") if payload else None
	return await repo_snapshot("/srv/mark", label)


@app.post("/tools/git_local_commit")
async def tool_git_local_commit(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	require_scope_write(request)
	message = payload.get("message", "chore: automated change")
	return await git_local_commit("/srv/mark", message)


@app.post("/tools/compose_cmd")
async def tool_compose_cmd(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	cmd = payload.get("cmd", "ps")
	service = payload.get("service")
	flags = payload.get("flags")
	if cmd != "ps":
		require_scope_write(request)
	return await compose_cmd(cmd, service, flags)


@app.get("/tools/compose_logs")
async def tool_compose_logs(service: str, tail: int = 200, since: str | None = None, _: None = Depends(require_auth)) -> dict:
	return await compose_logs(service, tail, since)


@app.post("/tools/container_exec")
async def tool_container_exec(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	require_scope_write(request)
	service = payload.get("service")
	cmd = payload.get("cmd")
	workdir = payload.get("workdir", "/srv/mark")
	timeout = int(payload.get("timeout", 300))
	return await container_exec(service, cmd, workdir, timeout)


@app.post("/tools/tests_run")
async def tool_tests_run(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	require_scope_write(request)
	service = payload.get("service")
	cmd = payload.get("cmd", "pytest -q")
	report_out = payload.get("report_out", "/data/mark/reports")
	return await tests_run(service, cmd, report_out)


@app.get("/tools/memory_search")
async def tool_memory_search(query: str, limit: int = 10, _: None = Depends(require_auth)) -> dict:
	return await memory_search(query, limit)


@app.get("/tools/search")
async def tool_search(query: str, limit: int = 10, _: None = Depends(require_auth)) -> dict:
	# Используем memory_search как основу для search
	return await memory_search(query, limit)


@app.post("/tools/memory_upsert")
async def tool_memory_upsert(payload: dict, request: Request, _: None = Depends(require_auth)) -> dict:
	require_scope_write(request)
	text = payload.get("text", "")
	metadata = payload.get("metadata") or {}
	return await memory_upsert(text, metadata)


@app.post("/tools/agent_run_task")
async def tool_agent_run_task(payload: dict, _: None = Depends(require_auth)) -> dict:
	task = payload.get("task", "")
	params = payload.get("params") or {}
	dry_run = payload.get("dry_run")
	return await agent_run_task(task, params, dry_run)


@app.get("/events")
async def sse_events(_: None = Depends(require_auth)):
	async def event_stream():
		for i in range(3):
			data = json.dumps({"type": "heartbeat", "i": i})
			yield f"data: {data}\n\n"
			await asyncio.sleep(5)
	return StreamingResponse(event_stream(), media_type="text/event-stream")
