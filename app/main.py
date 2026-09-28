from fastapi import FastAPI

from app.api.routes import auth

app = FastAPI(
    title="EVE Healthcare - Diagnostic Booking Service",
    description="Backend service for diagnostic test bookings and simulated payments.",
    version="0.1.0",
)

app.include_router(auth.router)


@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok"}
