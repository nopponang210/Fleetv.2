import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.db.database import Base, engine
from app import models # registers models
from app.routers.api import router as api_router
from app.routers.dashboard_v2 import router as dashboard_router
from app.line.webhook import router as line_router

Base.metadata.create_all(bind=engine) # Alembic can replace this in production migrations
app=FastAPI(title="FleetAI API", version="1.0.0")
app.include_router(dashboard_router); app.include_router(api_router); app.include_router(line_router)
static=Path(__file__).parent / "static"
app.mount("/static",StaticFiles(directory=static),name="static")
uploads=Path(os.getenv("UPLOAD_DIR","uploads")); uploads.mkdir(parents=True,exist_ok=True)
app.mount("/uploads",StaticFiles(directory=uploads),name="uploads")
@app.get("/health")
def health(): return {"status":"ok"}
@app.get("/login")
def login_page(): return FileResponse(static/"login.html",headers={"Cache-Control":"no-cache, no-store"})
@app.get("/dashboard")
def dashboard_page(): return FileResponse(static/"dashboard.html",headers={"Cache-Control":"no-cache, no-store"})
@app.get("/")
def home(): return FileResponse(static/"login.html",headers={"Cache-Control":"no-cache, no-store"})
