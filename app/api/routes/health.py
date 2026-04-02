from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.get("/health/ready")
async def readiness():
    """Checks that dependent services are reachable."""
    import httpx
    from app.config import get_settings
    s = get_settings()
    checks: dict[str, str] = {}

    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(f"{s.sandbox_url}/health")
            checks["sandbox"] = "ok" if r.status_code == 200 else "degraded"
    except Exception:
        checks["sandbox"] = "unreachable"

    try:
        from app.core.memory.vector_store import get_chroma
        client = await get_chroma()
        await client.heartbeat()
        checks["chromadb"] = "ok"
    except Exception:
        checks["chromadb"] = "unreachable"

    all_ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "ready" if all_ok else "degraded", "checks": checks},
    )
