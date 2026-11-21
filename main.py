"""
HUNGRY TOWN — AI Review & Delivery Intelligence System
Backend API (FastAPI)

Core loop implemented here:
    Understand -> Prioritize -> Investigate -> Decide -> Act -> Track

Reviews come in -> the AI Review Agent classifies them (sentiment, category,
severity, priority) -> serious/repeated delivery complaints can be sent to
the AI Delivery Agent ("Detective Mode") which inspects simulated
order/driver/route/traffic data, finds a probable root cause, and proposes
a corrective action -> the owner can run in AI-CONTROL (auto-apply) or
MANUAL-CONTROL (approve/reject) mode -> the outcome is tracked on every
order (open -> investigating -> resolved).
"""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ai_agent import analyze_review, investigate_order
from seed_data import ORDERS, seed_reviews

DB_PATH = os.path.join(os.path.dirname(__file__), "hungrytown.db")

app = FastAPI(title="Hungry Town AI Review & Delivery Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(reset: bool = False):
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    with get_db() as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_id TEXT NOT NULL,
                rating INTEGER NOT NULL,
                text TEXT NOT NULL,
                sentiment TEXT,
                category TEXT,
                severity TEXT,
                priority TEXT,
                explanation TEXT,
                recommended_action TEXT,
                status TEXT DEFAULT 'open',
                control_mode TEXT DEFAULT 'ai',
                decision TEXT,
                root_cause TEXT,
                created_at TEXT
            )
        """)

        # seed demo data once, so the dashboard is never empty on first run
        cur = db.execute("SELECT COUNT(*) AS c FROM reviews")
        if cur.fetchone()["c"] == 0:
            for r in seed_reviews():
                analysis = analyze_review(r["text"], r["rating"])
                db.execute(
                    """INSERT INTO reviews
                       (order_id, rating, text, sentiment, category, severity,
                        priority, explanation, recommended_action, status,
                        control_mode, created_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        r["order_id"], r["rating"], r["text"],
                        analysis["sentiment"], analysis["category"],
                        analysis["severity"], analysis["priority"],
                        analysis["explanation"], analysis["recommended_action"],
                        "open", "ai", datetime.utcnow().isoformat(),
                    ),
                )


init_db()


# --------------------------------------------------------------------------- #
# Schemas
# --------------------------------------------------------------------------- #

class ReviewIn(BaseModel):
    order_id: str
    rating: int
    text: str


class ControlModeIn(BaseModel):
    control_mode: str  # "ai" | "manual"


class DecisionIn(BaseModel):
    decision: str  # "approve" | "reject"


# --------------------------------------------------------------------------- #
# Routes — Reviews (Understand -> Prioritize)
# --------------------------------------------------------------------------- #

@app.post("/api/reviews")
def submit_review(review: ReviewIn):
    """Customer submits a review. The AI Review Agent classifies it immediately."""
    analysis = analyze_review(review.text, review.rating)

    with get_db() as db:
        cur = db.execute(
            """INSERT INTO reviews
               (order_id, rating, text, sentiment, category, severity,
                priority, explanation, recommended_action, status,
                control_mode, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                review.order_id, review.rating, review.text,
                analysis["sentiment"], analysis["category"],
                analysis["severity"], analysis["priority"],
                analysis["explanation"], analysis["recommended_action"],
                "open", "ai", datetime.utcnow().isoformat(),
            ),
        )
        review_id = cur.lastrowid
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        return dict(row)


@app.get("/api/reviews")
def list_reviews():
    with get_db() as db:
        rows = db.execute("SELECT * FROM reviews ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/api/reviews/{review_id}")
def get_review(review_id: int):
    with get_db() as db:
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Review not found")
        return dict(row)


# --------------------------------------------------------------------------- #
# Routes — Detective Mode (Investigate -> Decide)
# --------------------------------------------------------------------------- #

@app.post("/api/reviews/{review_id}/investigate")
def investigate(review_id: int):
    """
    AI Delivery Agent: pulls the (simulated) order/driver/route/traffic data
    for this order, reasons about a probable root cause, and proposes a
    corrective action. Does NOT apply the action — that depends on control mode.
    """
    with get_db() as db:
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Review not found")

        order_data = ORDERS.get(row["order_id"])
        if not order_data:
            raise HTTPException(404, f"No simulated order data for {row['order_id']}")

        result = investigate_order(order_data, dict(row))

        db.execute(
            "UPDATE reviews SET status='investigating', root_cause=? WHERE id=?",
            (result["root_cause"], review_id),
        )

        return {
            "order_data": order_data,
            "root_cause": result["root_cause"],
            "recommended_action": result["recommended_action"],
            "confidence": result["confidence"],
        }


@app.post("/api/reviews/{review_id}/control-mode")
def set_control_mode(review_id: int, body: ControlModeIn):
    if body.control_mode not in ("ai", "manual"):
        raise HTTPException(400, "control_mode must be 'ai' or 'manual'")
    with get_db() as db:
        db.execute("UPDATE reviews SET control_mode=? WHERE id=?", (body.control_mode, review_id))
    return {"ok": True}


@app.post("/api/reviews/{review_id}/decision")
def apply_decision(review_id: int, body: DecisionIn):
    """
    Human-in-the-loop: owner approves or rejects the AI's recommended action.
    Approving marks the order resolved and 'executes' the digital action.
    """
    if body.decision not in ("approve", "reject"):
        raise HTTPException(400, "decision must be 'approve' or 'reject'")

    with get_db() as db:
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Review not found")

        new_status = "resolved" if body.decision == "approve" else "open"
        db.execute(
            "UPDATE reviews SET decision=?, status=? WHERE id=?",
            (body.decision, new_status, review_id),
        )
        row = db.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
        return dict(row)


# --------------------------------------------------------------------------- #
# Routes — Statistics (Business Intelligence)
# --------------------------------------------------------------------------- #

@app.get("/api/stats")
def stats():
    with get_db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM reviews").fetchall()]

    total = len(rows)
    satisfied = len([r for r in rows if r["sentiment"] == "positive"])
    unsatisfied = len([r for r in rows if r["sentiment"] == "negative"])
    neutral = total - satisfied - unsatisfied

    by_priority = {"P1": 0, "P2": 0, "P3": 0}
    by_category = {}
    for r in rows:
        if r["priority"] in by_priority:
            by_priority[r["priority"]] += 1
        cat = r["category"] or "other"
        by_category[cat] = by_category.get(cat, 0) + 1

    resolved = len([r for r in rows if r["status"] == "resolved"])

    return {
        "total_orders": 500,  # simulated business volume
        "total_reviews": total,
        "satisfied": satisfied,
        "unsatisfied": unsatisfied,
        "neutral": neutral,
        "satisfaction_rate": round((satisfied / total) * 100, 1) if total else 0,
        "by_priority": by_priority,
        "by_category": by_category,
        "resolved": resolved,
        "open": total - resolved,
    }


@app.post("/api/reset")
def reset_demo():
    """Convenience endpoint for judges/testers to reset to a clean demo state."""
    init_db(reset=True)
    return {"ok": True}


@app.get("/api/health")
def health():
    return {"status": "ok", "product": "Hungry Town AI Review & Delivery Intelligence"}
