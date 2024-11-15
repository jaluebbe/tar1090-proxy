from io import BytesIO
from pathlib import Path
import gzip
import httpx
import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, FileResponse

app = FastAPI()

TAR1090_DB_PATH = Path("../tar1090-db/db")
TAR1090_PATH = Path("../tar1090/html")
CONFIG_FILE_PATH = Path("./config.js")  # Set to None if not provided
TARGET_URL = "http://my-dump1090-host:8080"


@app.get("/", include_in_schema=False)
async def root(request: Request):
    return RedirectResponse("/index.html")


if CONFIG_FILE_PATH and CONFIG_FILE_PATH.exists():

    @app.get("/config.js", include_in_schema=False)
    async def serve_config_js():
        return FileResponse(
            CONFIG_FILE_PATH, media_type="application/javascript"
        )


async def proxy_request(
    request: Request, base_url: str, path: str = ""
) -> Response:
    query_params = "&".join(
        [
            f"{key}={value}" if value else key
            for key, value in dict(request.query_params).items()
        ]
    )
    url = f"{base_url}/{path}?{query_params}"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, headers={"Accept-Encoding": "gzip"})
        headers = dict(response.headers)
        if headers.get("content-encoding") == "gzip":
            gzip_buffer = BytesIO()
            with gzip.GzipFile(mode="wb", fileobj=gzip_buffer) as gz_file:
                gz_file.write(response.content)
            content = gzip_buffer.getvalue()
            headers["content-length"] = str(len(content))
        else:
            content = response.content
    return Response(
        content=content,
        status_code=response.status_code,
        headers=headers,
    )


@app.api_route("/re-api/", methods=["GET"])
async def proxy_re_api(request: Request):
    return await proxy_request(request, f"{TARGET_URL}/re-api")


@app.api_route("/data/{path:path}", methods=["GET"])
async def proxy_data(request: Request, path: str):
    return await proxy_request(request, f"{TARGET_URL}/data", path)


@app.api_route("/chunks/{path:path}", methods=["GET"])
async def proxy_chunks(request: Request, path: str):
    return await proxy_request(request, f"{TARGET_URL}/chunks", path)


@app.middleware("http")
async def add_gzip_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/db2/") and request.url.path.endswith(
        ".js"
    ):
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Type"] = "application/javascript"
    return response


app.mount("/db2", StaticFiles(directory=TAR1090_DB_PATH), name="tar1090-db")
app.mount("/", StaticFiles(directory=TAR1090_PATH), name="tar1090")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)