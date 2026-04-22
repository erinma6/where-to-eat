#!/usr/bin/env python3
"""
Weekly sync script: scrapes the public Google Maps shared list, upserts
new/updated places into Supabase, and hard-deletes any places no longer
in the list.

Usage:
    python scripts/sync_places.py
"""

import os
import sys
import time
import json
import requests
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from src.db.supabase_client import RestaurantRepository
from src.api.openai_client import SyncOpenAIClient
from scripts.scrape_places import scrape_saved_places

GOOGLE_API_KEY = os.getenv("GOOGLE_PLACES_API_KEY")

_PRICE_LEVEL_MAP = {
    "PRICE_LEVEL_INEXPENSIVE": 1,
    "PRICE_LEVEL_MODERATE": 2,
    "PRICE_LEVEL_EXPENSIVE": 3,
    "PRICE_LEVEL_VERY_EXPENSIVE": 4,
}

_CUISINE_KEYWORDS = {
    "Korean": ["korean", "korea", "bibimbap", "bulgogi", "kimchi", "samgyeopsal", "kalbi", "kbbq", "seoul"],
    "Japanese": ["japanese", "japan", "sushi", "ramen", "izakaya", "tempura", "tonkatsu", "udon", "soba", "yakitori", "teriyaki", "bento"],
    "Chinese": ["chinese", "china", "dim sum", "szechuan", "cantonese", "dumpling", "wok", "peking", "bao", "soup dumplings", "sichuan", "hainan"],
    "Thai": ["thai", "thailand", "pad thai", "green curry", "massaman", "tom yum"],
    "Vietnamese": ["vietnamese", "vietnam", "pho", "bahn mi", "banh mi", "viet", "ca phe", "banh cuon"],
    "Indian": ["indian", "india", "curry", "tandoor", "tikka", "masala", "naan", "dosa", "biryani", "paneer"],
    "Italian": ["italian", "italy", "pizza", "pasta", "trattoria", "osteria", "enoteca", "gelato", "cucina", "cacio", "pomodoro"],
    "Mexican": ["mexican", "mexico", "taco", "burrito", "quesadilla", "enchilada", "guacamole", "taqueria"],
    "Peruvian": ["peruvian", "peru", "lomo", "ceviche", "anticucho"],
    "Mediterranean": ["mediterranean", "greek", "turkish", "lebanese", "falafel", "hummus", "kebab", "shawarma", "pita"],
    "French": ["french", "france", "bistro", "brasserie", "crepe", "croissant", "patisserie", "macaron"],
    "BBQ": ["bbq", "barbecue", "smokehouse", "smoked", "pit", "ribs", "brisket"],
    "Seafood": ["seafood", "fish", "lobster", "oyster", "crab", "shrimp", "clam", "mussel"],
    "Steakhouse": ["steakhouse", "steak", "churrascaria", "gaucho", "prime rib"],
    "American": ["diner", "burger", "pub", "grill", "tavern", "wings", "cheesesteak", "deli", "sandwich"],
    "Caribbean": ["caribbean", "jamaican", "jerk", "trinidad", "cuban"],
    "Filipino": ["filipino", "philippines", "pinoy", "adobo", "lechon"],
    "Hawaiian": ["hawaiian", "hawaii", "poke", "plate lunch", "acai"],
    "African": ["african", "ethiopian", "eritrean", "nigerian", "west african", "moroccan"],
    "Spanish": ["spanish", "tapas", "paella", "sangria"],
    "Cafe": ["cafe", "coffee", "barista", "espresso", "latte", "cappuccino", "tea", "boba", "bubble tea", "matcha"],
    "Bakery": ["bakery", "bakeshop", "donut", "pastry", "bread", "bagel", "biscuit"],
    "Ice Cream": ["ice cream", "gelato", "frozen yogurt", "sorbet", "paletas"],
    "Ramen": ["ramen", "tonkotsu", "shoyu", "shio", "miso ramen"],
    "Dim Sum": ["dim sum", "dimsum", "yum cha"],
}

# Maps Google Places API types to cuisine tags (None = too generic to use)
_GOOGLE_TYPE_TO_CUISINE = {
    "cafe": "Cafe",
    "cafeteria": "Cafe",
    "bakery": "Bakery",
    "bar": "Bar",
    "night_club": "Nightclub",
    "restaurant": None,
    "food": None,
}


def _infer_cuisine(name: str, types: list) -> list:
    """Infer cuisine tags from restaurant name keywords and Google Places types."""
    name_lower = name.lower()
    cuisines = []

    for cuisine, keywords in _CUISINE_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                cuisines.append(cuisine)
                break

    for t in types:
        mapped = _GOOGLE_TYPE_TO_CUISINE.get(t)
        if mapped and mapped not in cuisines:
            cuisines.append(mapped)

    return cuisines


def _get_reviews(place_id: str) -> list[str]:
    """Fetch up to 5 review texts for a place (separate call, only used when needed)."""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": "reviews",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            reviews = resp.json().get("reviews", [])[:5]
            return [
                r["text"]["text"] for r in reviews
                if r.get("text", {}).get("text")
            ]
    except Exception:
        pass
    return []


def _enrich_from_reviews(name: str, reviews: list[str], openai: SyncOpenAIClient, need_cuisine: bool = False) -> dict:
    """Single LLM call to extract vibes, notes, and optionally cuisine from reviews.

    Returns a dict with keys: "vibes", "notes", and "cuisine" (only when need_cuisine=True).
    Returns {} if the LLM call fails or reviews are empty.
    """
    if not reviews:
        return {}

    cuisine_field = (
        '\n- "cuisine": array of cuisine types (e.g., ["Italian", "Pizza"])'
        if need_cuisine else ""
    )

    prompt = f"""Analyze this restaurant and its reviews.

Restaurant: {name}

Reviews:
{chr(10).join(reviews[:3])}

Return a JSON object with:{cuisine_field}
- "vibes": array using only these values: ["casual", "date night", "romantic", "family-friendly", "lively", "quiet", "cozy", "trendy", "upscale", "fine dining", "dive bar", "hidden gem", "local favorite"]
- "notes": 2-3 sentence summary of what makes this place worth visiting

Return only the JSON, nothing else."""

    try:
        response = openai.chat_completion(
            [
                {"role": "system", "content": "You are a restaurant expert. Extract structured information from reviews."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=200,
        ).strip()

        if "```json" in response:
            response = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            response = response.split("```")[1].split("```")[0]

        return json.loads(response.strip())
    except Exception:
        return {}


def _extract_neighborhood(address_components: list) -> str | None:
    """Extract neighborhood from Google Places addressComponents.

    Priority: neighborhood (e.g. Williamsburg) → sublocality_level_1 (borough: Brooklyn)
    → locality when non-NYC (e.g. Jersey City, Fort Lee).
    """
    by_type = {t: c["longText"] for c in address_components for t in c.get("types", [])}

    if "neighborhood" in by_type:
        return by_type["neighborhood"]
    if "sublocality_level_1" in by_type:
        return by_type["sublocality_level_1"]
    locality = by_type.get("locality")
    if locality and locality != "New York":
        return locality
    return None


def _build_embedding_text(place: dict, cuisine_tags: list[str], neighborhood: str | None = None,
                          vibe_tags: list[str] | None = None, notes: str | None = None) -> str:
    """Build the text representation used for embedding (matches generate_embeddings.py format)."""
    parts = [place.get("name", ""), place.get("address", ""), neighborhood or ""]
    parts.extend(cuisine_tags)
    parts.extend(vibe_tags or [])
    if notes:
        parts.append(notes)
    return ", ".join([p for p in parts if p])


def _parse_place_response(p: dict, fallback_name: str = "") -> dict:
    return {
        "google_place_id": p.get("id"),
        "name": p.get("displayName", {}).get("text", fallback_name),
        "address": p.get("formattedAddress", ""),
        "rating": p.get("rating"),
        "total_ratings": p.get("userRatingCount"),
        "price_level": _PRICE_LEVEL_MAP.get(p.get("priceLevel", "")),
        # Prefixed with _ so they're stripped before DB upsert; used for enrichment
        "_types": p.get("types", []),
        "_address_components": p.get("addressComponents", []),
    }


def search_place_by_name(name: str) -> dict | None:
    """Resolve a restaurant name to Google Places data."""
    url = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": (
            "places.id,places.displayName,places.formattedAddress,"
            "places.rating,places.userRatingCount,places.priceLevel,places.types,"
            "places.addressComponents"
        ),
    }
    body = {"textQuery": f"{name} NYC", "maxResultCount": 1}

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        if resp.status_code == 200:
            places = resp.json().get("places", [])
            if places:
                return _parse_place_response(places[0], fallback_name=name)
    except Exception as e:
        print(f"  API error for '{name}': {e}")
    return None


def get_place_by_id(place_id: str) -> dict | None:
    """Fetch place details directly by Google Place ID."""
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": GOOGLE_API_KEY,
        "X-Goog-FieldMask": (
            "id,displayName,formattedAddress,rating,userRatingCount,priceLevel,types,addressComponents"
        ),
    }
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return _parse_place_response(resp.json())
    except Exception as e:
        print(f"  API error for place ID '{place_id}': {e}")
    return None


def sync():
    scraped = scrape_saved_places()
    if not scraped:
        print("No places scraped — aborting to avoid accidental mass deletion.")
        sys.exit(1)

    repo = RestaurantRepository()
    existing_ids = repo.get_all_google_ids()

    resolved = []
    not_found = 0

    for i, item in enumerate(scraped):
        name = item.get("name", "")
        place_id = item.get("place_id")
        label = name or place_id or f"item {i+1}"
        print(f"[{i+1}/{len(scraped)}] {label[:60]}")

        # Prefer direct place ID lookup; fall back to name search
        if place_id:
            place = get_place_by_id(place_id)
        elif name:
            place = search_place_by_name(name)
        else:
            not_found += 1
            continue

        if not place or not place.get("google_place_id"):
            print(f"  -> Not resolved, skipping")
            not_found += 1
            continue

        resolved.append(place)
        gid = place["google_place_id"]
        action = "Updated" if gid in existing_ids else "Added"
        print(f"  -> {action}: {place['name']}")

        time.sleep(0.1)

    if resolved:
        # Deduplicate by google_place_id (keep first occurrence)
        seen_ids = set()
        unique_resolved = []
        for p in resolved:
            gid = p["google_place_id"]
            if gid not in seen_ids:
                unique_resolved.append(p)
                seen_ids.add(gid)

        db_records = [{k: v for k, v in p.items() if not k.startswith("_")} for p in unique_resolved]
        try:
            repo.upsert_restaurants_batch(db_records)
        except Exception as e:
            print(f"Error during batch upsert: {e}. Attempting individual upserts...")
            for record in db_records:
                try:
                    repo.upsert_restaurant(record)
                except Exception as record_error:
                    print(f"  Failed to upsert {record.get('name', 'Unknown')}: {record_error}")

    # Enrich newly added places: cuisine, neighborhood, vibes, notes, embedding
    new_places = [p for p in resolved if p["google_place_id"] not in existing_ids]
    if new_places:
        openai = SyncOpenAIClient()
        for place in new_places:
            tags = _infer_cuisine(place["name"], place.get("_types", []))
            neighborhood = _extract_neighborhood(place.get("_address_components", []))

            # Fetch reviews once — used for LLM cuisine fallback + vibes + notes
            reviews = _get_reviews(place["google_place_id"])
            llm_data = {}
            if reviews:
                print(f"  LLM enriching {place['name']}...")
                llm_data = _enrich_from_reviews(
                    place["name"], reviews, openai, need_cuisine=not tags
                )
                if not tags and llm_data.get("cuisine"):
                    tags = llm_data["cuisine"]

            # Generate embedding — always, so the place appears in vector search
            embedding = openai.get_embedding(_build_embedding_text(
                place, tags,
                neighborhood=neighborhood,
                vibe_tags=llm_data.get("vibes"),
                notes=llm_data.get("notes"),
            ))

            update_data = {"embedding": embedding, "updated_at": "now()"}
            if tags:
                update_data["cuisine_tags"] = tags
            if neighborhood:
                update_data["neighborhood"] = neighborhood
            if llm_data.get("vibes"):
                update_data["vibe_tags"] = llm_data["vibes"]
            if llm_data.get("notes"):
                update_data["notes"] = llm_data["notes"]

            repo.table.update(update_data).eq(
                "google_place_id", place["google_place_id"]
            ).execute()
            print(f"  Enriched {place['name']}: cuisine={tags or 'none'}, "
                  f"neighborhood={neighborhood or 'none'}, vibes={llm_data.get('vibes') or 'none'}")

    resolved_ids = {p["google_place_id"] for p in resolved}
    added = len(resolved_ids - existing_ids)
    updated = len(resolved_ids & existing_ids)

    to_delete = existing_ids - resolved_ids
    deleted = 0
    if to_delete:
        print(f"\nDeleting {len(to_delete)} removed places...")
        deleted = repo.delete_many_by_google_ids(to_delete)

    print(f"\n--- Sync complete ---")
    print(f"  Added:   {added}")
    print(f"  Updated: {updated}")
    print(f"  Deleted: {deleted}")
    print(f"  Skipped: {not_found}")
    print(f"  Total in DB: {repo.count()}")


if __name__ == "__main__":
    sync()
