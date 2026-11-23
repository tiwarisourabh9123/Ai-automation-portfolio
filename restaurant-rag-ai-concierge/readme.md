
# Spice & Flame Bistro — Hybrid RAG AI Concierge & Ordering System

An end-to-end AI-powered restaurant concierge, table reservation engine, and conversational food ordering application built for **Spice & Flame Bistro (Koramangala, Bengaluru)**. 

The system combines **Hybrid Retrieval-Augmented Generation (Dense + BM25 Sparse Search with Reciprocal Rank Fusion)** in Qdrant with **Google Gemini Structured Outputs (Pydantic)** to deliver hallucination-guarded menu/policy Q&A, multi-turn table reservations, automated food ordering with policy validation, human desk handoff, and a password-protected staff dashboard.

---

## Key Features

### 1. Hybrid RAG Menu & Policy Intelligence
* **Grounded Knowledge Retrieval:** Answers customer queries strictly from `data/menu.json` and `data/policies.md` with source citations displayed under every response.
* **Hybrid Search (Dense + Sparse + RRF):** Combines semantic vector search (`gemini-embedding-001`, 768 dimensions) with deterministic MD5-hashed BM25 keyword sparse vectors inside **Qdrant**, fused via **Reciprocal Rank Fusion (RRF)** for accurate dish, price, and policy matching.
* **Proactive Allergen & Pricing Alerts:** Automatically surfaces exact prices in `₹` and warns customers about allergens (such as dairy or cashew) based on retrieved menu records.
* **Multilingual Support (English & Hinglish):** Natively understands and responds to English, Hindi, and Hinglish queries (e.g., *"khana khuwnga"*) without extra translation layers.

### 2. Conversational Table Reservations (`TBL-XXXXX`)
* **Multi-Turn Slot Collection:** Collects customer name, guest count (`1–12`), and preferred dining time across natural back-and-forth conversation.
* **Dual Booking Channels:** Supports reservations both via the **AI Chat Widget** and the **Website Reservation Form**, persisting all bookings to `data/reservations.json` with unique `TBL-XXXXX` IDs.
* **Capacity Guardrails:** Enforces the 1–12 online guest limit and directs larger groups to the restaurant desk.

### 3. Conversational Food Ordering & Policy Validation (`ORD-XXXXX`)
* **Natural Language Order Parsing:** Extracts ordered dishes, quantities, customer name, phone number, and delivery address (or Pickup) from chat.
* **Automated Total & Rule Validation:** Cross-references ordered items against `data/menu.json` to calculate exact `₹` totals and enforces restaurant policies:
  * **Minimum Delivery Order:** Rejects home delivery orders below `₹250` while allowing Pickup.
  * **Payment Eligibility:** Automatically flags orders `≤ ₹1,500` as **COD Eligible** and orders `> ₹1,500` as **UPI/Card Prepayment Required**.
* **Persistent Order Logging:** Saves validated orders to `data/orders.json` with unique `ORD-XXXXX` confirmation IDs.

### 4. Production Reliability & Human Handoff
* **Structured JSON Output (`ConciergeResponse`):** Uses Pydantic schema enforcement (`response_mime_type="application/json"`) to eliminate multi-turn tool-calling/thought-signature errors on Gemini 3.x models.
* **Automatic Model Failover:** Automatically falls back from `gemini-3.5-flash-lite` to `gemini-3.8-flash` on `503 UNAVAILABLE` demand spikes.
* **Human Desk Escalation:** Recognizes requests to speak with staff or a manager and provides direct phone/WhatsApp escalation (`+91-80-4123-9876`).

### 5. Password-Protected Staff Dashboard (`/bookings`)
* **Session-Gated Access:** Protects `/bookings` behind a staff login gate (`BOOKINGS_PASSWORD` via environment variables) with one-click **Lock Page** session termination.
* **Unified Live View:** Displays real-time **Chat Food Orders** (`data/orders.json`) and **Table Reservations** (`data/reservations.json`) in a clean responsive dashboard.

---

## Tech Stack & Tools Used

| Layer | Technology / Tool | Purpose |
| :--- | :--- | :--- |
| **Backend Framework** | Python 3, Flask | REST API (`/api/chat`, `/api/reserve`), session auth, Jinja2 templating |
| **LLM & Reasoning** | Google Gemini API (`gemini-3.5-flash-lite`, `gemini-3.8-flash`) | Multi-turn conversational reasoning, intent routing, and automatic `503` failover |
| **Structured Outputs** | Pydantic (`BaseModel`) | Type-safe JSON schema (`ConciergeResponse`) for reliable booking & order extraction |
| **Embeddings** | `gemini-embedding-001` (768-dim) | Multilingual dense semantic embeddings for queries and documents |
| **Vector Database** | Qdrant (Local Persistent Storage) | Hybrid search combining dense vectors + BM25 sparse vectors with RRF fusion |
| **Frontend & UI** | HTML5, Vanilla JavaScript, Tailwind CSS | Responsive storefront, floating AI Concierge chat widget, and staff admin dashboard |
| **Data Persistence** | JSON (`menu.json`, `policies.md`, `reservations.json`, `orders.json`) | Lightweight structured knowledge base and transactional storage |

---

## Project Structure

```text
restaurant-rag-ai-concierge/
├── app.py                     # Flask backend, hybrid search, Gemini structured JSON & auth routes
├── ingest.py                  # Embedding & Qdrant hybrid collection ingestion script
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variable template
├── data/
│   ├── menu.json              # Restaurant dishes, prices, spice levels & allergens
│   ├── policies.md            # Delivery radius, COD limits, reservation & allergy policies
│   ├── reservations.json      # Saved table bookings (auto-generated)
│   └── orders.json            # Saved chat food orders (auto-generated)
├── static/
│   └── js/
│       └── chat_widget.js     # Floating AI chat UI, history state & source citations
├── templates/
│   ├── index.html             # Customer storefront, menu grid & reservation form
│   └── admin.html             # Password-protected staff orders & bookings dashboard
└── images/                    # Project screenshots for documentation
