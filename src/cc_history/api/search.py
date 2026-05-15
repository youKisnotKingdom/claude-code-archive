from fastapi import APIRouter, Query

from cc_history.services import indexer, search

router = APIRouter()


def serialize_result(result: search.SearchResult) -> dict[str, str | float | None]:
    return {
        "session_id": result.session_id,
        "user": result.user,
        "project": result.project,
        "project_decoded": result.project_decoded,
        "uuid": result.uuid,
        "role": result.role,
        "text": result.text,
        "timestamp": result.timestamp,
        "rank": result.rank,
    }


@router.get("/search")
def search_messages(
    q: str = Query(default=""),
    user: str | None = Query(default=None),
) -> dict[str, object]:
    summary = indexer.index_all_sessions()
    results = [serialize_result(result) for result in search.search_messages(q, user=user)]
    return {
        "query": q,
        "user": user,
        "index": {
            "scanned_sessions": summary.scanned_sessions,
            "indexed_sessions": summary.indexed_sessions,
            "skipped_sessions": summary.skipped_sessions,
        },
        "results": results,
    }
