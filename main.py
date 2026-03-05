from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from bson import ObjectId
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://127.0.0.1:27017")
DB_NAME = os.getenv("DB_NAME", "media")
COLLECTION = os.getenv("COLLECTION", "movies")

client = MongoClient(MONGO_URI)
db = client[DB_NAME]
col = db[COLLECTION]

app = FastAPI(title="API MongoDB Search - Films")

# --------- Utils ---------
def oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except Exception:
        raise HTTPException(status_code=400, detail="ID MongoDB invalide")

def serialize(doc: dict) -> dict:
    doc["id"] = str(doc["_id"])
    del doc["_id"]
    return doc

# --------- Modèles ---------
class MovieCreate(BaseModel):
    titre: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    genre: str = Field(..., min_length=1)          # filtre additionnel obligatoire possible
    annee: int = Field(..., ge=1888)               # premier film ~1888
    note: float = Field(..., ge=0, le=10)          # filtre possible

# --------- CRUD minimal ---------

# POST /items : créer un document
@app.post("/items", status_code=201)
def create_item(payload: MovieCreate):
    doc = payload.model_dump()
    result = col.insert_one(doc)
    created = col.find_one({"_id": result.inserted_id})
    return serialize(created)

# GET /items/:id : lire un document
@app.get("/items/{id}")
def get_item(id: str):
    doc = col.find_one({"_id": oid(id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Document introuvable")
    return serialize(doc)

# GET /items : liste (pagination facultative)
@app.get("/items")
def list_items(page: int = Query(1, ge=1), limit: int = Query(10, ge=1, le=100)):
    skip = (page - 1) * limit
    docs = list(col.find().skip(skip).limit(limit))
    return {
        "page": page,
        "limit": limit,
        "count": len(docs),
        "items": [serialize(d) for d in docs]
    }

# --------- Recherche obligatoire ---------
# GET /search?keyword=... (regex insensible à la casse sur 2 champs: titre + description)
# + filtre additionnel au moins: genre=...
@app.get("/search")
def search(
    keyword: str = Query(..., min_length=1),
    genre: Optional[str] = None,                 # filtre additionnel (exigence)
    note_min: Optional[float] = Query(None, ge=0, le=10),
    annee_max: Optional[int] = Query(None, ge=1888)
):
    # Recherche sur au moins 2 champs via $regex (case-insensitive)
    text_query = {
        "$or": [
            {"titre": {"$regex": keyword, "$options": "i"}},
            {"description": {"$regex": keyword, "$options": "i"}}
        ]
    }

    filters = []
    if genre:
        filters.append({"genre": genre})
    if note_min is not None:
        filters.append({"note": {"$gte": note_min}})
    if annee_max is not None:
        filters.append({"annee": {"$lte": annee_max}})

    # Combine recherche + filtres
    final_query = {"$and": [text_query] + filters} if filters else text_query

    docs = list(col.find(final_query).limit(50))
    return {
        "keyword": keyword,
        "filters": {"genre": genre, "note_min": note_min, "annee_max": annee_max},
        "count": len(docs),
        "items": [serialize(d) for d in docs]
    }