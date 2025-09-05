import os
from fastapi import FastAPI
from src.api.routes import router, def_static_files, def_textures_files
import uvicorn

app = FastAPI()

# Mount static files and router
app.mount("/static", def_static_files, name="static")
app.mount("/textures", def_textures_files, name="textures")
app.include_router(router)

if __name__ == "__main__":
    # Bind to 0.0.0.0 and the provided PORT on Render; use localhost in dev
    port = int(os.getenv("PORT", "8000"))
    on_render = os.getenv("PORT") is not None
    host = "0.0.0.0" if on_render else "127.0.0.1"
    reload = False if on_render else True
    if on_render:
        print(f"Starting server for Render on {host}:{port}")
    else:
        print("Starting server in development mode...")
        print(f"Open your browser and navigate to http://{host}:{port}")
    uvicorn.run("app:app", host=host, port=port, reload=reload)
    