from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import threads, chat

app = FastAPI(title="Agentic RAG")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router)
app.include_router(chat.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
