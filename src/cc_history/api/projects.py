from fastapi import APIRouter

from cc_history.services import scanner

router = APIRouter()


@router.get("/users/{user}/projects")
def get_projects(user: str) -> dict[str, list[dict[str, str]]]:
    projects = [
        {
            "name": project,
            "decoded": scanner.decode_project_name(project),
        }
        for project in scanner.list_projects(user)
    ]
    return {"projects": projects}
