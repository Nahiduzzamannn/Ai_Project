from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.v1.router import api_router

app = FastAPI(title=settings.APP_NAME)

# Allow your React app to call this backend
origins = [
    "http://localhost:5173",  # Vite default
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],   # GET/POST/PUT/DELETE...
    allow_headers=["*"],   # Authorization, Content-Type, etc.
    expose_headers=["X-Paper-Seed", "Content-Disposition"],
)

app.include_router(api_router, prefix=settings.API_V1_PREFIX)

@app.get("/")
def root():
    return {"message": "Backend running"}