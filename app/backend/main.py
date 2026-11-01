from fastapi import FastAPI

app = FastAPI(
    title="Raincheck Backend",
    description="Backend API for the Raincheck weather dashboard",
    version="1.0.0",
)


@app.get("/")
def root():
    return {
        "application": "Raincheck",
        "service": "backend",
        "status": "running",
    }


@app.get("/health")
def health():
    return {
        "status": "healthy",
    }