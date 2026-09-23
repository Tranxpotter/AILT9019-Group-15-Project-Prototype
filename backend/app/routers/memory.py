"""Memory endpoints: previously suggested restaurants + the user's own reviews."""
from fastapi import APIRouter, HTTPException

from .. import db
from ..schemas import ReviewIn

router = APIRouter(prefix="/api", tags=["memory"])


@router.get("/memory")
def memory():
    return {
        "suggestions": db.list_suggestions(limit=100),
        "reviews": db.list_reviews(),
    }


@router.delete("/memory/suggestions")
def clear_memory():
    db.clear_suggestions()
    return {"ok": True}


@router.post("/reviews")
def add_review(review: ReviewIn):
    if not db.get_restaurant(review.restaurant_id):
        raise HTTPException(status_code=404, detail="Restaurant not found")
    return db.add_review(review.restaurant_id, review.rating, review.comment)


@router.get("/reviews")
def reviews():
    return db.list_reviews()
