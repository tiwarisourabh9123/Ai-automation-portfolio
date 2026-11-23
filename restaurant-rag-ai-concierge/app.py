import hashlib
import json
import os
import re
import uuid
from datetime import datetime
from dotenv import load_dotenv
from flask import Flask, jsonify, redirect, render_template, request, session, url_for
from google import genai
from google.genai import types
from pydantic import BaseModel
from qdrant_client import QdrantClient, models

load_dotenv()
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "spice-flame-secret-key-2026")
BOOKINGS_PASSWORD = os.environ.get("BOOKINGS_PASSWORD", "st9123")

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
qdrant = QdrantClient(path="./qdrant_db")
COLLECTION_NAME = "restaurant_knowledge"
RESERVATIONS_FILE = "data/reservations.json"
ORDERS_FILE = "data/orders.json"


class ConciergeResponse(BaseModel):
    reply: str
    action_type: str  # "none", "book_table", or "order_food"
    customer_name: str
    guests: int
    time_slot: str
    items_summary: str
    delivery_address: str
    phone: str


SYSTEM_PROMPT = """You are the AI Concierge for Spice & Flame Bistro in Koramangala, Bengaluru.
Answer customer questions using ONLY the retrieved menu and policy records provided below.

Rules:
1. If a dish, policy, or detail is not in the context, say: "I do not see that in our current menu or policies. You can call or WhatsApp our desk team at +91-80-4123-9876."
2. Always mention prices in Rs and warn clearly if any allergen (like dairy or cashew) is present.
3. HUMAN HANDOFF: If the customer asks to speak to a real person, staff member, or manager, share +91-80-4123-9876 and tell them to tap Call Desk or WhatsApp Desk below.
4. TABLE BOOKING:
   - Set action_type = "book_table" ONLY when you have ALL THREE: customer_name, guests (1-12), and time_slot.
   - If any is missing, set action_type = "none" and ask politely for the missing details in reply.
5. FOOD ORDERING:
   - Set action_type = "order_food" ONLY when you have ALL FOUR: valid menu dishes with quantities in items_summary (e.g. "2x Paneer Tikka Platter, 1x Dal Tadka & Jeera Rice Bowl"), customer_name, phone, and delivery_address (or "Dine-in / Pickup").
   - Note delivery policy: minimum Rs 250 for delivery within 6 km of Koramangala; COD up to Rs 1,500.
   - If any of the 4 details is missing, set action_type = "none" and politely ask for the missing details in reply.
6. Keep replies concise, warm, and accurate."""


def _read_json(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []


def _write_json(path, records):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)


def _save_booking(customer_name: str, guests: int, time_slot: str, source: str) -> dict:
    if guests < 1 or guests > 12:
        return {
            "status": "rejected",
            "reason": "Online bookings support 1 to 12 guests. Please call +91-80-4123-9876 for larger groups.",
        }
    records = _read_json(RESERVATIONS_FILE)
    booking_id = f"TBL-{uuid.uuid4().hex[:5].upper()}"
    records.append({
        "booking_id": booking_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "customer_name": customer_name,
        "guests": guests,
        "time_slot": time_slot,
        "source": source,
    })
    _write_json(RESERVATIONS_FILE, records)
    return {"status": "confirmed", "booking_id": booking_id}


def _save_food_order(customer_name: str, phone: str, items_summary: str, delivery_address: str) -> dict:
    menu = _read_json("data/menu.json")
    total = 0
    matched_items = []
    lower_summary = items_summary.lower()
    for dish in menu:
        if dish["name"].lower() in lower_summary:
            m = re.search(r"(\d+)\s*x?\s*" + re.escape(dish["name"].lower()), lower_summary)
            qty = int(m.group(1)) if m else 1
            total += dish["price"] * qty
            matched_items.append(f"{qty}x {dish['name']} (Rs {dish['price'] * qty})")

    final_items = ", ".join(matched_items) if matched_items else items_summary
    if total > 0 and total < 250 and "pickup" not in delivery_address.lower():
        return {
            "status": "rejected",
            "reason": f"Your order total is Rs {total}, which is below our Rs 250 minimum for home delivery. Add one more item or choose Pickup!",
        }

    records = _read_json(ORDERS_FILE)
    order_id = f"ORD-{uuid.uuid4().hex[:5].upper()}"
    payment_note = "COD Eligible" if total <= 1500 else "UPI/Card Prepayment Required (>Rs 1500)"
    records.append({
        "order_id": order_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %I:%M %p"),
        "customer_name": customer_name,
        "phone": phone,
        "items": final_items,
        "total": f"Rs {total}" if total > 0 else "Menu Rate",
        "delivery_address": delivery_address,
        "payment_note": payment_note,
    })
    _write_json(ORDERS_FILE, records)
    return {"status": "confirmed", "order_id": order_id, "total": total, "payment_note": payment_note}


def compute_bm25_sparse(text: str) -> models.SparseVector:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stopwords = {"the", "is", "at", "which", "on", "and", "a", "an", "for", "to", "in", "of", "with", "are", "our", "we"}
    counts = {}
    for tok in tokens:
        if tok in stopwords or len(tok) < 2:
            continue
        idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
        counts[idx] = counts.get(idx, 0.0) + 1.0
    indices = sorted(counts.keys())
    return models.SparseVector(indices=indices, values=[counts[i] for i in indices])


def hybrid_retrieve(query: str, top_k: int = 3) -> list[dict]:
    dense_vec = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=[query],
        config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY", output_dimensionality=768),
    ).embeddings[0].values
    hits = qdrant.query_points(
        collection_name=COLLECTION_NAME,
        prefetch=[
            models.Prefetch(query=dense_vec, using="dense", limit=6),
            models.Prefetch(query=compute_bm25_sparse(query), using="sparse", limit=6),
        ],
        query=models.FusionQuery(fusion=models.Fusion.RRF),
        limit=top_k,
    ).points
    return [hit.payload for hit in hits]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/bookings", methods=["GET", "POST"])
def view_bookings():
    error = None
    if request.method == "POST":
        entered_password = request.form.get("password", "")
        if entered_password == BOOKINGS_PASSWORD:
            session["bookings_authenticated"] = True
            return redirect(url_for("view_bookings"))
        error = "Incorrect password. Please try again."

    if not session.get("bookings_authenticated"):
        return render_template("admin.html", locked=True, error=error, reservations=[], orders=[])

    return render_template(
        "admin.html",
        locked=False,
        error=None,
        reservations=list(reversed(_read_json(RESERVATIONS_FILE))),
        orders=list(reversed(_read_json(ORDERS_FILE))),
    )


@app.route("/bookings/logout")
def bookings_logout():
    session.pop("bookings_authenticated", None)
    return redirect(url_for("view_bookings"))


@app.route("/api/reserve", methods=["POST"])
def api_reserve():
    data = request.get_json()
    name = data.get("customer_name", "").strip()
    guests = int(data.get("guests", 0))
    time_slot = data.get("time_slot", "").strip()
    if not name or not time_slot or guests < 1:
        return jsonify({"error": "Please enter valid name, guest count, and time."}), 400
    result = _save_booking(customer_name=name, guests=guests, time_slot=time_slot, source="Website Form")
    if result.get("status") == "rejected":
        return jsonify({"error": result["reason"]}), 400
    return jsonify(result)


@app.route("/api/chat", methods=["POST"])
def chat():
    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()
        history = data.get("history", [])
        if not user_message:
            return jsonify({"error": "Message is required"}), 400

        matches = hybrid_retrieve(user_message)
        context_str = "\n".join([f"- {m['text']}" for m in matches])

        contents = [
            types.Content(role=t["role"], parts=[types.Part.from_text(text=t["text"])])
            for t in history[-8:]
        ]
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"Retrieved Context:\n{context_str}\n\nCustomer Message: {user_message}")],
            )
        )

        cfg = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ConciergeResponse,
            temperature=0.1,
        )
        try:
            response = gemini_client.models.generate_content(model="gemini-3.5-flash-lite", contents=contents, config=cfg)
        except Exception as api_err:
            if "503" in str(api_err) or "UNAVAILABLE" in str(api_err):
                response = gemini_client.models.generate_content(model="gemini-3.8-flash", contents=contents, config=cfg)
            else:
                raise

        parsed = json.loads(response.text)
        reply_text = parsed["reply"]
        action = parsed.get("action_type", "none")

        if action == "book_table" and parsed.get("customer_name") and parsed.get("guests", 0) > 0 and parsed.get("time_slot"):
            booking = _save_booking(parsed["customer_name"], int(parsed["guests"]), parsed["time_slot"], "AI Chatbot")
            reply_text = (
                f"{reply_text} (Booking ID: {booking['booking_id']})"
                if booking["status"] == "confirmed"
                else booking["reason"]
            )

        elif action == "order_food" and parsed.get("customer_name") and parsed.get("items_summary") and parsed.get("phone"):
            order = _save_food_order(
                parsed["customer_name"],
                parsed["phone"],
                parsed["items_summary"],
                parsed.get("delivery_address") or "Pickup",
            )
            if order["status"] == "confirmed":
                tot_txt = f" | Total: Rs {order['total']}" if order["total"] > 0 else ""
                reply_text = f"{reply_text} (Order ID: {order['order_id']}{tot_txt} • {order['payment_note']})"
            else:
                reply_text = order["reason"]

        return jsonify({"reply": reply_text, "sources": [m["title"] for m in matches]})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Server error: {str(e)}"}), 500


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, port=5000)