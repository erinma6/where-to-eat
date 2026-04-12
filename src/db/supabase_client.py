"""
Supabase database client.
"""

import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()


def get_client() -> Client:
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY")
    return create_client(url, key)


class RestaurantRepository:
    """Repository for restaurant CRUD operations."""

    def __init__(self, client: Optional[Client] = None):
        self.client = client or get_client()
        self.table = self.client.table("restaurants")

    def upsert_restaurant(self, data: Dict[str, Any]) -> Dict[str, Any]:
        result = self.table.upsert(data).execute()
        return result.data[0] if result.data else None

    def upsert_restaurants_batch(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        result = self.table.upsert(data).execute()
        return result.data

    def get_by_google_id(self, google_place_id: str) -> Optional[Dict[str, Any]]:
        result = self.table.select("*").eq("google_place_id", google_place_id).execute()
        return result.data[0] if result.data else None

    def get_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        result = self.table.select("*").eq("id", id).execute()
        return result.data[0] if result.data else None

    def get_all(self, limit: int = 500) -> List[Dict[str, Any]]:
        result = self.table.select("*").order("rating", desc=True).limit(limit).execute()
        return result.data

    def search_by_cuisine(self, cuisine: str, limit: int = 50) -> List[Dict[str, Any]]:
        result = self.table.select("*").contains("cuisine_tags", [cuisine]).limit(limit).execute()
        return result.data

    def update_personal_notes(self, id: str, notes: str) -> Dict[str, Any]:
        result = self.table.update({
            "personal_notes": notes,
            "updated_at": "now()"
        }).eq("id", id).execute()
        return result.data[0] if result.data else None

    def delete(self, id: str) -> bool:
        result = self.table.delete().eq("id", id).execute()
        return len(result.data) > 0

    def delete_by_google_id(self, google_place_id: str) -> bool:
        result = self.table.delete().eq("google_place_id", google_place_id).execute()
        return len(result.data) > 0

    def delete_many_by_google_ids(self, google_place_ids: set) -> int:
        result = self.table.delete().in_("google_place_id", list(google_place_ids)).execute()
        return len(result.data)

    def get_all_google_ids(self) -> set:
        result = self.table.select("google_place_id").execute()
        return {row["google_place_id"] for row in result.data if row.get("google_place_id")}

    def count(self) -> int:
        # Uses server-side COUNT to avoid fetching rows
        result = self.table.select("id", count="exact").execute()
        return result.count or 0


if __name__ == "__main__":
    repo = RestaurantRepository()
    print(f"Total restaurants: {repo.count()}")
