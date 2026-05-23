"""FastAPI Web应用"""
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    from kb.web import dependencies
    if dependencies._sqlite_instance:
        dependencies._sqlite_instance.close()
        dependencies._sqlite_instance = None

app = FastAPI(title="Knowledge Brain", description="知识大脑管理API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

from kb.web.routes import dashboard, items, search, tags, graph, topics, mining, recommendations, wiki, backup, settings
app.include_router(dashboard.router, prefix="/api", tags=["Dashboard"])
app.include_router(items.router, prefix="/api", tags=["Items"])
app.include_router(search.router, prefix="/api", tags=["Search"])
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

@app.get("/", response_class=HTMLResponse)
async def root():
    index_file = static_dir / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<html><body><h1>Knowledge Brain API</h1><p><a href='/api/docs'>API Docs</a></p></body></html>"

@app.get("/health")
async def health():
    return {"status": "ok"}
