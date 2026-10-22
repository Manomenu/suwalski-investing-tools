import uvicorn

from suwinvtools_server.settings import settings

if __name__ == "__main__":
    uvicorn.run("suwinvtools_server.app:app", host=settings.host, port=settings.port, reload=False)
