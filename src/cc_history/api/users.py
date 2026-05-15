from fastapi import APIRouter

from cc_history.services import scanner

router = APIRouter()


@router.get("/users")
def get_users() -> dict[str, list[str]]:
    return {"users": scanner.list_users()}
