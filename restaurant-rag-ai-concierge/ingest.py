import hashlib
import json
import os
import re
import uuid
from dotenv import load_dotenv
from google import genai
from google.genai import types
from qdrant_client import QdrantClient, models

load_dotenv()

gemini_client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
qdrant = QdrantClient(path="./qdrant_db")
COLLECTION_NAME = "restaurant_knowledge"


def compute_bm25_sparse(text: str) -> models.SparseVector:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stopwords = {"the", "is", "at", "which", "on", "and", "a", "an", "for", "to", "in", "of", "with", "are", "our", "we"}
    counts: dict[int, float] = {}
    for tok in tokens:
        if tok in stopwords or len(tok) < 2:
            continue
        idx = int(hashlib.md5(tok.encode("utf-8")).hexdigest()[:8], 16)
        counts[idx] = counts.get(idx, 0.0) + 1.0
    indices = sorted(counts.keys())
    values = [counts[i] for i in indices]
    return models.SparseVector(indices=indices, values=values)


def embed_texts(texts: list[str]) -> list[list[float]]:
    response = gemini_client.models.embed_content(
        model="gemini-embedding-001",
        contents=texts,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=768,
        ),
    )
    return [emb.values for emb in response.embeddings]


def run_ingestion():
    documents, points_meta = [], []

    # 1. Load Menu Items
    with open("data/menu.json", "r", encoding="utf-8") as f:
        menu_items = json.load(f)

    for item in menu_items:
        allergen_text = ", ".join(item["allergens"]) if item["allergens"] else "None"
        doc_text = (
            f"Dish: {item['name']} ({item['category']}) | Price: ₹{item['price']} | "
            f"Spice: {item['spice_level']} | Vegan: {item['is_vegan']} | "
            f"Allergens: {allergen_text}. Description: {item['description']}"
        )
        documents.append(doc_text)
        points_meta.append({
            "source_type": "menu",
            "title": item["name"],
            "text": doc_text,
            "price": item["price"],
            "is_vegan": item["is_vegan"],
            "allergens": allergen_text,
        })

    # 2. Load & Chunk Restaurant Policies by Markdown Section
    with open("data/policies.md", "r", encoding="utf-8") as f:
        raw_policies = f.read().strip()

    for section in raw_policies.split("\n# "):
        clean_sec = section.lstrip("# ").strip()
        if not clean_sec:
            continue
        lines = clean_sec.split("\n", 1)
        title = lines[0].strip()
        body = lines[1].strip() if len(lines) > 1 else ""
        doc_text = f"Restaurant Policy - {title}: {body}"
        documents.append(doc_text)
        points_meta.append({
            "source_type": "policy",
            "title": f"Policy: {title}",
            "text": doc_text,
            "price": 0,
            "is_vegan": False,
            "allergens": "None",
        })

    if qdrant.collection_exists(COLLECTION_NAME):
        qdrant.delete_collection(COLLECTION_NAME)

    qdrant.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config={
            "dense": models.VectorParams(size=768, distance=models.Distance.COSINE),
        },
        sparse_vectors_config={
            "sparse": models.SparseVectorParams(modifier=models.Modifier.IDF),
        },
    )

    dense_embeddings = embed_texts(documents)
    points = [
        models.PointStruct(
            id=str(uuid.uuid4()),
            vector={
                "dense": dense_vec,
                "sparse": compute_bm25_sparse(doc_text),
            },
            payload=meta,
        )
        for doc_text, dense_vec, meta in zip(documents, dense_embeddings, points_meta)
    ]

    qdrant.upsert(collection_name=COLLECTION_NAME, points=points)
    print(f"Hybrid Index Complete: {len(points)} records (menu + policies) stored in Qdrant!")


if __name__ == "__main__":
    run_ingestion()
