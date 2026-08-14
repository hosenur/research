from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/hello")
async def hello() -> dict[str, str]:
    """Return a small greeting to verify that the API is running."""
    return {"message": "Hello, World!"}
