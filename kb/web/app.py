"""FastAPI Web应用"""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Knowledge Brain starting up...")
    try:
        from kb.web.dependencies import get_config
        from kb.scheduler.backup_scheduler import init_scheduler
        config = get_config()
        init_scheduler(config)
    except Exception as e:
        logger.warning(f"Failed to start backup scheduler: {e}")
    yield
    # Shutdown
    logger.info("Knowledge Brain shutting down...")
    from kb.web import dependencies
    from kb.scheduler.backup_scheduler import stop_scheduler
    stop_scheduler()
    if dependencies._sqlite_instance:
        dependencies._sqlite_instance.close()
        dependencies._sqlite_instance = None
    if dependencies._chroma_instance:
        try:
            dependencies._chroma_instance.close()
        except Exception:
            pass
        dependencies._chroma_instance = None


app = FastAPI(
    title="Knowledge Brain",
    description="知识大脑管理API - 个人知识管理系统",
    version="0.2.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url}: {exc}", exc_info=True)
    return JSONResponse(status_code=500, content={"error": str(exc)})


from kb.web.routes import dashboard, items, search, tags, graph, topics, mining, recommendations, wiki, backup, settings, collect as collect_route
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(items.router, prefix="/api", tags=["Items"])
app.include_router(search.router, prefix="/api", tags=["Search"])
app.include_router(collect_route.router, prefix="/api", tags=["Collect"])
app.include_router(tags.router, prefix="/api", tags=["Tags"])
app.include_router(graph.router, prefix="/api", tags=["Graph"])
app.include_router(topics.router, prefix="/api", tags=["Topics"])
app.include_router(mining.router, prefix="/api", tags=["Mining"])
app.include_router(recommendations.router, prefix="/api", tags=["Recommendations"])
app.include_router(wiki.router, prefix="/api", tags=["Wiki"])
app.include_router(backup.router, prefix="/api", tags=["Backup"])
app.include_router(settings.router, prefix="/api", tags=["Settings"])

static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# Cache the index.html content
_index_html_cache = None


@app.get("/", response_class=HTMLResponse)
async def root():
    global _index_html_cache
    if _index_html_cache is None:
        index_file = static_dir / "index.html"
        if index_file.exists():
            _index_html_cache = index_file.read_text(encoding="utf-8")
        else:
            _index_html_cache = "<html><body><h1>Knowledge Brain API</h1><p><a href='/api/docs'>API Docs</a></p></body></html>"
    return _index_html_cache


@app.get("/health")
async def health():
    try:
        from kb.web.dependencies import get_config
        config = get_config()
        status = config.validate_services()
        return {"status": "ok", "services": status}
    except Exception:
        return {"status": "ok", "services": {"embedding_available": False, "llm_available": False}}
