"""
AI agents for Hungry Town.

1. Review Agent (`analyze_review`) — sends customer reviews to Google Gemini
   for sentiment, category, severity, priority, explanation, and action.

2. Delivery Agent (`investigate_order`) — "Detective Mode". Sends the
   simulated order/driver/route/traffic data plus the complaint to Gemini
   to identify a likely root cause and corrective action.

Gemini is the primary AI engine. If the Gemini API is unavailable, the
application falls back to deterministic Python rules so the local demo can
continue running.
"""

import json
import os
import re
from typing import Optional

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-3.6-flash"

CATEGORY_KEYWORDS = {
    "delivery": ["late", "delay", "delayed", "slow", "took", "hours", "min",
                 "never arrived", "driver", "cold by the time", "waiting"],
    "food_quality": ["cold", "stale", "taste", "tasteless", "raw", "burnt",
                     "spoiled", "bad food", "quality"],
    "packaging": ["spilled", "leaked", "packaging", "box", "container",
                  "messy", "damaged"],
    "service": ["rude", "staff", "behavior", "unprofessional", "attitude",
                "customer service", "support"],
}

POSITIVE_WORDS = ["good", "great", "amazing", "excellent", "love", "fast",
                   "friendly", "perfect", "awesome", "delicious", "fresh",
                   "on time", "quick"]
NEGATIVE_WORDS = ["bad", "late", "cold", "rude", "worst", "terrible",
                   "awful", "slow", "never", "disappointed", "spilled",
                   "stale", "raw", "poor", "delay", "delayed"]


def _rule_based_analysis(text: str, rating: int) -> dict:
    lower = text.lower()

    # --- sentiment ---------------------------------------------------- #
    pos_hits = sum(1 for w in POSITIVE_WORDS if w in lower)
    neg_hits = sum(1 for w in NEGATIVE_WORDS if w in lower)

    if rating >= 4 and neg_hits == 0:
        sentiment = "positive"
    elif rating <= 2 or neg_hits > pos_hits:
        sentiment = "negative"
    elif neg_hits > 0 and pos_hits > 0:
        sentiment = "mixed"
    else:
        sentiment = "positive" if pos_hits >= neg_hits else "neutral"

    # --- category -------------------------------------------------------#
    scores = {cat: sum(1 for kw in kws if kw in lower)
              for cat, kws in CATEGORY_KEYWORDS.items()}
    top_cat = max(scores, key=scores.get)
    category = top_cat if scores[top_cat] > 0 else ("general" if sentiment == "positive" else "other")

    # --- severity / priority --------------------------------------------#
    if sentiment == "positive":
        severity, priority = "none", "P3"
    else:
        strong_negative_markers = ["never arrived", "worst", "terrible",
                                    "awful", "hours", "rude"]
        is_strong = any(m in lower for m in strong_negative_markers) or rating == 1
        if is_strong:
            severity, priority = "high", "P1"
        elif sentiment == "negative":
            severity, priority = "medium", "P2"
        else:
            severity, priority = "low", "P3"

    # --- explanation + recommended action -------------------------------#
    if sentiment == "positive":
        explanation = "Customer expressed satisfaction with the order."
        recommended_action = "No action needed. Log as positive feedback."
    else:
        readable_cat = category.replace("_", " ")
        explanation = f"Customer reported a {readable_cat} issue with rating {rating}/5."
        if category == "delivery":
            recommended_action = "Run Detective Mode to check driver load, route and traffic for this order."
        elif category == "food_quality":
            recommended_action = "Flag to kitchen team for quality review."
        elif category == "packaging":
            recommended_action = "Flag to packaging/handling team."
        elif category == "service":
            recommended_action = "Flag to staff training / team coaching."
        else:
            recommended_action = "Review manually to determine next step."

    return {
        "sentiment": sentiment,
        "category": category,
        "severity": severity,
        "priority": priority,
        "explanation": explanation,
        "recommended_action": recommended_action,
    }


def _gemini_analysis(text: str, rating: int) -> Optional[dict]:
    """Analyze a review with the current Google GenAI Python SDK."""
    if not GEMINI_API_KEY:
        print("[ai_agent] GEMINI_API_KEY is not set; using Python fallback.")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""You are the AI review analyst for Hungry Town, a restaurant.
Analyze this customer review and return ONLY valid JSON.

Rating: {rating}/5
Review: "{text}"

Use exactly these fields:
- sentiment: positive, negative, neutral, or mixed
- category: delivery, food_quality, packaging, service, general, or other
- severity: none, low, medium, or high
- priority: P1, P2, or P3 (P1 is most urgent)
- explanation: one concise sentence explaining the classification
- recommended_action: one concise, practical action for the business

Do not add markdown or any other fields."""

        schema = {
            "type": "OBJECT",
            "properties": {
                "sentiment": {"type": "STRING", "enum": ["positive", "negative", "neutral", "mixed"]},
                "category": {"type": "STRING", "enum": ["delivery", "food_quality", "packaging", "service", "general", "other"]},
                "severity": {"type": "STRING", "enum": ["none", "low", "medium", "high"]},
                "priority": {"type": "STRING", "enum": ["P1", "P2", "P3"]},
                "explanation": {"type": "STRING"},
                "recommended_action": {"type": "STRING"},
            },
            "required": [
                "sentiment", "category", "severity",
                "priority", "explanation", "recommended_action"
            ],
        }

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        parsed = json.loads(response.text)
        print("[ai_agent] Gemini review analysis: SUCCESS")
        return parsed

    except Exception as e:
        print(f"[ai_agent] Gemini review failed, falling back to rules: {e}")
        return None

def analyze_review(text: str, rating: int) -> dict:
    # Try Gemini first. If Gemini is unavailable or fails, use the
    # deterministic rule-based fallback so the demo can still work.
    llm_result = _gemini_analysis(text, rating)
    if llm_result:
        return llm_result
    return _rule_based_analysis(text, rating)


# --------------------------------------------------------------------------- #
# Detective Mode
# --------------------------------------------------------------------------- #

def _gemini_investigation(order_data: dict, review: dict) -> Optional[dict]:
    """Use Gemini to investigate the likely operational root cause."""
    if not GEMINI_API_KEY:
        print("[ai_agent] GEMINI_API_KEY is not set; using Python fallback.")
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GEMINI_API_KEY)

        prompt = f"""You are an operations detective for Hungry Town.

Customer complaint:
"{review.get('text', '')}"

Simulated operational data for this order:
{json.dumps(order_data, indent=2)}

Determine the most likely operational root cause. Use only the supplied data
and clearly distinguish a likely cause from certainty.

Return ONLY valid JSON with:
- root_cause: one or two concise sentences
- recommended_action: one concrete corrective action
- confidence: a number from 0 to 1"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "root_cause": {"type": "STRING"},
                "recommended_action": {"type": "STRING"},
                "confidence": {"type": "NUMBER"},
            },
            "required": ["root_cause", "recommended_action", "confidence"],
        }

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )

        parsed = json.loads(response.text)
        parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))
        print("[ai_agent] Gemini detective investigation: SUCCESS")
        return parsed

    except Exception as e:
        print(f"[ai_agent] Gemini investigation failed, falling back to rules: {e}")
        return None

def investigate_order(order_data: dict, review: dict) -> dict:
    """
    Reasons over simulated operational data to find a probable root cause
    for a delivery complaint, and proposes a corrective action.
    Tries a real LLM call first, falls back to rule-based reasoning.
    """
    llm_result = _gemini_investigation(order_data, review)
    if llm_result:
        return llm_result

    orders_assigned = order_data.get("driver_orders_assigned", 1)
    traffic = order_data.get("traffic", "normal")
    expected_min = order_data.get("expected_delivery_min", 20)
    actual_min = order_data.get("actual_delivery_min", 20)
    delay = actual_min - expected_min

    reasons = []
    confidence = 0.5

    if orders_assigned >= 3:
        reasons.append(f"the assigned driver had {orders_assigned} simultaneous orders")
        confidence += 0.2
    if traffic == "heavy":
        reasons.append("heavy traffic was reported on the delivery route")
        confidence += 0.2
    if delay >= 30:
        reasons.append(f"the order ran {delay} minutes over the expected delivery time")
        confidence += 0.1

    if not reasons:
        root_cause = "No clear operational anomaly found — this may be an isolated incident."
        recommended_action = "Send a personalized apology and a discount code to the customer."
        confidence = 0.4
    else:
        root_cause = "Likely cause: " + " and ".join(reasons) + "."
        if orders_assigned >= 3:
            recommended_action = (
                f"Reduce concurrent order load on drivers during peak hours "
                f"and reassign overloaded orders to nearby available drivers."
            )
        elif traffic == "heavy":
            recommended_action = "Recalculate route to avoid current traffic hotspot for future orders in this zone."
        else:
            recommended_action = "Escalate to delivery operations manager for review."

    confidence = min(confidence, 0.95)

    return {
        "root_cause": root_cause,
        "recommended_action": recommended_action,
        "confidence": round(confidence, 2),
    }
