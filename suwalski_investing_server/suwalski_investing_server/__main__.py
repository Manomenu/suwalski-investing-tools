import uvicorn

from suwalski_investing_server.settings import settings

if __name__ == "__main__":
    uvicorn.run("suwalski_investing_server.app:app", host=settings.host, port=settings.port, reload=False)
