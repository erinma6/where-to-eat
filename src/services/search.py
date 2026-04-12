"""
Hybrid search service combining structured and vector search.
"""

import os
from typing import Optional, List, Dict, Any
from supabase import create_client, Client
from pydantic import BaseModel
from src.api.openai_client import OpenAIClient
from dotenv import load_dotenv

load_dotenv()


class SearchFilters(BaseModel):
    """Structured search filters extracted from query."""
    cuisine: Optional[List[str]] = None
    vibes: Optional[List[str]] = None
    neighborhood: Optional[str] = None
    min_rating: Optional[float] = None
    budget: Optional[str] = None  # "budget", "moderate", "expensive"


class SearchService:
    """Hybrid search combining structured and vector search."""

    # Borough to neighborhood mapping for NYC
    BOROUGH_NEIGHBORHOODS = {
        "manhattan": ["Chelsea", "East Village", "Financial District", "Flatbush", "Gramercy",
                     "Hell's Kitchen", "Lower East Side", "Midtown", "Murray Hill", "SoHo",
                     "Tribeca", "Upper East Side", "Upper West Side", "West Village", "Greenwich Village",
                     "Nolita", "NoHo", "Chinatown", "Little Italy", "Harlem", "Inwood", "Washington Heights"],
        "brooklyn": ["Brooklyn Heights", "Bedford-Stuyvesant", "Carroll Gardens", "Downtown Brooklyn",
                    "DUMBO", "Park Slope", "Prospect Heights", "Sunset Park", "Williamsburg",
                    "Bushwick", "Crown Heights", "Clinton Hill", "Gowanus", "Red Hook", "Boerum Hill",
                    "Greenpoint", "Bay Ridge", " Bensonhurst", "Sheepshead Bay", "Midwood", "Flatbush"],
        "queens": ["Astoria", "Bayside", "Elmhurst", "Flushing", "Forest Hills", "Jackson Heights",
                  "Jamaica", "Long Island City", "Richmond Hill", "Ridgewood", "Sunnyside",
                  "Woodside", "Kew Gardens", "Whitestone", "Douglaston", "Little Neck"],
        "bronx": ["Bronx", "Riverdale", "Fordham", "Highbridge", "Kingsbridge", "Morris Park", "Pelham Bay"],
        "staten island": ["St. George", "Stapleton", "Great Kills", "Tottenville", "Annadale"],
    }

    # Cuisine synonym mapping - user search term -> database term
    CUISINE_TO_DB = {
        "coffee": "Cafe",
        "café": "Cafe",
        "tea": "Cafe",
        "bubble tea": "Cafe",
        "bagels": "Bakery",
        "bagel": "Bakery",
        "donuts": "Bakery",
        "donut": "Bakery",
        "ice cream": "Dessert",
        "gelato": "Dessert",
        "pizza": "Italian",
        "sushi": "Japanese",
        "ramen": "Japanese",
        "korean bbq": "Korean",
        "korean": "Korean",
        "thai": "Thai",
        "vietnamese": "Vietnamese",
        "chinese": "Chinese",
        "mexican": "Mexican",
        "tacos": "Mexican",
        "taco": "Mexican",
        "burritos": "Mexican",
        "indian": "Indian",
        "french": "French",
        "bbq": "BBQ",
        "barbecue": "BBQ",
        "seafood": "Seafood",
        "fish": "Seafood",
        "brunch": "American",
        "breakfast": "American",
        "lunch": "American",
        "dinner": "American",
    }

    # Location synonyms - common ways users refer to NYC areas
    LOCATION_SYNONYMS = {
        "nyc": "manhattan",  # Default to Manhattan for NYC
        "new york": "manhattan",
        "new york city": "manhattan",
        "the city": "manhattan",
        "nYC": "manhattan",
    }

    # Reverse mapping: neighborhood -> borough
    NEIGHBORHOOD_TO_BOROUGH = {}
    for borough, neighborhoods in BOROUGH_NEIGHBORHOODS.items():
        for n in neighborhoods:
            NEIGHBORHOOD_TO_BOROUGH[n.lower()] = borough

    def __init__(self, supabase_url: Optional[str] = None, supabase_key: Optional[str] = None):
        self.supabase_url = supabase_url or os.getenv("SUPABASE_URL")
        self.supabase_key = supabase_key or os.getenv("SUPABASE_SERVICE_KEY")
        self.client: Client = create_client(self.supabase_url, self.supabase_key)
        self.openai = OpenAIClient()

    def _rerank_by_rating(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Re-rank search results by combining semantic similarity with rating.

        Score = 0.6 * similarity + 0.4 * normalized_rating
        This gives 60% weight to semantic relevance and 40% to rating quality.
        """
        if not results:
            return results

        def calculate_score(r):
            similarity = r.get('similarity', 0)
            # Get rating, default to 3.5 if not present (midpoint)
            rating = r.get('rating', 3.5) or 3.5
            # Normalize rating from 0-5 scale to 0-1
            normalized_rating = rating / 5.0
            # Weighted combination: 60% similarity, 40% rating
            return 0.6 * similarity + 0.4 * normalized_rating

        # Sort by combined score (descending)
        reranked = sorted(results, key=calculate_score, reverse=True)
        return reranked

    async def hybrid_search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Perform hybrid search combining structured and vector similarity.

        Uses embeddings for semantic search combined with structured filters.
        Falls back to pure semantic search if structured data (cuisine_tags,
        vibe_tags) is not populated.

        Args:
            query: Natural language query
            filters: Optional structured filters
            limit: Max results to return

        Returns:
            List of matching restaurants with similarity scores
        """
        # Generate embedding for the query
        query_embedding = await self.openai.get_embedding(query)

        # Check if we have structured data to filter by
        # If not, rely on pure semantic search
        has_structured_data = False  # Would check if cuisine_tags/vibe_tags are populated

        if filters:
            # Check if neighborhood is a borough and map to specific neighborhoods
            neighborhood = filters.neighborhood
            borough_neighborhoods = None  # For borough-level filtering

            if neighborhood:
                neighborhood_lower = neighborhood.lower()
                # Map location synonyms (e.g., "NYC" -> "manhattan")
                if neighborhood_lower in self.LOCATION_SYNONYMS:
                    neighborhood_lower = self.LOCATION_SYNONYMS[neighborhood_lower]
                # If it's a borough, get the list of neighborhoods in that borough
                if neighborhood_lower in self.BOROUGH_NEIGHBORHOODS:
                    borough_neighborhoods = self.BOROUGH_NEIGHBORHOODS[neighborhood_lower]
                    neighborhood = None  # Don't use exact match, use semantic instead

            # Only use filters if we have actual filter criteria
            use_cuisine = filters.cuisine and len(filters.cuisine) > 0
            use_vibes = filters.vibes and len(filters.vibes) > 0
            use_neighborhood = neighborhood is not None
            use_rating = filters.min_rating is not None
            use_borough = borough_neighborhoods is not None

            # If any filter is specified, try to use hybrid search
            if use_cuisine or use_vibes or use_neighborhood or use_rating or use_borough:
                # Map cuisine synonyms to database terms (e.g., "coffee" -> "Cafe")
                def map_cuisine(c):
                    mapped = self.CUISINE_TO_DB.get(c.lower(), c.capitalize())
                    return mapped
                query_cuisine = [map_cuisine(c) for c in filters.cuisine] if use_cuisine else None

                # Capitalize vibes
                query_vibes = [v.capitalize() for v in filters.vibes] if use_vibes else None

                # Use semantic search (no exact neighborhood filter) when borough is specified
                # This lets the embedding find relevant places in that area
                result = self.client.rpc("hybrid_search", {
                    "query_embedding": query_embedding,
                    "query_cuisine": query_cuisine,
                    "query_vibes": query_vibes,
                    "query_neighborhood": neighborhood,  # Will be None if borough was specified
                    "min_rating": filters.min_rating if use_rating else None,
                    "limit_count": limit * 2  # Get more results, we'll filter by borough afterward
                }).execute()

                if result.data:
                    results = result.data

                    # Re-rank results to prioritize both semantic similarity AND rating
                    # Using weighted combination: 60% similarity + 40% rating (normalized)
                    results = self._rerank_by_rating(results)

                    # If borough was specified, filter results to only include neighborhoods in that borough
                    # OR restaurants whose address contains the borough/neighborhood
                    if use_borough:
                        borough_lower = filters.neighborhood.lower()
                        valid_neighborhoods = [n.lower() for n in borough_neighborhoods]
                        search_terms = [borough_lower] + valid_neighborhoods

                        def is_in_borough(r):
                            # Check neighborhood field
                            r_neighborhood = r.get('neighborhood')
                            if r_neighborhood and r_neighborhood.lower() in valid_neighborhoods:
                                return True
                            # Check address contains borough or neighborhood
                            addr = r.get('address', '').lower()
                            if any(term in addr for term in search_terms):
                                return True
                            return False

                        results = [r for r in results if is_in_borough(r)]

                    return results[:limit]

        # Fallback: pure semantic search (vector similarity only)
        # This works even without structured data
        result = self.client.rpc("hybrid_search", {
            "query_embedding": query_embedding,
            "query_cuisine": None,
            "query_vibes": None,
            "query_neighborhood": None,
            "min_rating": None,
            "limit_count": limit
        }).execute()

        results = result.data if result.data else []
        # Re-rank by rating
        results = self._rerank_by_rating(results)
        return results

    async def basic_search(
        self,
        query: str,
        filters: Optional[SearchFilters] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Basic search without embeddings - returns top rated restaurants.
        Note: Filters are parsed but not applied yet due to Supabase issues.
        TODO: Fix filter application when Supabase is stable.
        """
        # For now, just return top rated restaurants
        # The query parsing works but Supabase has issues with some filters
        result = self.client.table("restaurants").select(
            "name, rating, address, price_level, total_ratings"
        ).order("rating", desc=True).limit(limit).execute()
        return result.data

    async def search_by_cuisine(
        self,
        cuisine: str,
        neighborhood: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search restaurants by cuisine tag."""
        result = self.client.table("restaurants").select("*").contains(
            "cuisine_tags", [cuisine]
        )

        if neighborhood:
            result = result.eq("neighborhood", neighborhood)

        result = result.order("rating", desc=True).limit(limit).execute()
        return result.data

    async def search_by_vibe(
        self,
        vibe: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search restaurants by vibe tag."""
        result = self.client.table("restaurants").select("*").contains(
            "vibe_tags", [vibe]
        ).order("rating", desc=True).limit(limit).execute()
        return result.data

    async def get_restaurant_by_id(self, id: str) -> Optional[Dict[str, Any]]:
        """Get a single restaurant by ID."""
        result = self.client.table("restaurants").select("*").eq("id", id).execute()
        return result.data[0] if result.data else None

    async def search_by_name(self, name: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search for a restaurant by name using semantic similarity."""
        # First try exact/partial match
        result = self.client.table("restaurants").select("*").ilike(
            "name", f"%{name}%"
        ).order("rating", desc=True).limit(limit).execute()

        if result.data:
            return result.data

        # If no exact match, try semantic similarity using embeddings
        try:
            query_embedding = await self.openai.get_embedding(name)
            # Use the hybrid_search function but with no cuisine/vibes filters
            result = self.client.rpc("hybrid_search", {
                "query_embedding": query_embedding,
                "query_cuisine": None,
                "query_vibes": None,
                "query_neighborhood": None,
                "min_rating": None,
                "limit_count": limit
            }).execute()
            return result.data if result.data else []
        except Exception:
            return []

    async def get_all_restaurants(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get all restaurants."""
        result = self.client.table("restaurants").select("*").order(
            "rating", desc=True
        ).limit(limit).execute()
        return result.data


class QueryParser:
    """Parse natural language queries into structured filters."""

    # Cuisine synonyms mapping
    CUISINE_SYNONYMS = {
        "korean": ["korean", "korea"],
        "japanese": ["japanese", "japan", "sushi", "ramen"],
        "chinese": ["chinese", "china", "dim sum", "szechuan", "cantonese"],
        "mexican": ["mexican", "mexico", "tacos", "burritos"],
        "italian": ["italian", "italy", "pizza", "pasta"],
        "thai": ["thai", "thailand"],
        "vietnamese": ["vietnamese", "vietnam", "pho", "bahn mi"],
        "indian": ["indian", "india", "curry"],
        "french": ["french", "france", "bistro"],
        "bbq": ["bbq", "barbecue", "smoked"],
        "seafood": ["seafood", "fish", "lobster", "oysters"],
    }

    # Vibe synonyms
    VIBE_SYNONYMS = {
        "casual": ["casual", "laid back", "relaxed", "no fuss"],
        "date night": ["date night", "romantic", "date", "romance"],
        "family-friendly": ["family-friendly", "family", "kids", "kid-friendly"],
        "lively": ["lively", "vibrant", "energetic", "busy", "happening"],
        "quiet": ["quiet", "peaceful", "cozy", "intimate"],
        "trendy": ["trendy", "trendy", "hip", "popular"],
        "upscale": ["upscale", "fancy", "nice", "special occasion"],
        "budget": ["budget", "cheap", "affordable", "inexpensive", "value"],
        "fine dining": ["fine dining", "fine dining", "elegant"],
    }

    def __init__(self, openai_client: Optional[OpenAIClient] = None):
        self.client = openai_client or OpenAIClient()

    async def parse(self, query: str) -> SearchFilters:
        """
        Parse natural language query into structured filters.

        Args:
            query: Natural language query like "Korean food in Brooklyn"

        Returns:
            SearchFilters with extracted criteria
        """
        system_prompt = """You are a query parser for a restaurant recommendation system.
Extract the following from the user's query:

1. CUISINE: What cuisine types are mentioned? (korean, italian, etc.)
2. VIBES: What vibes/atmosphere are mentioned? (casual, date night, etc.)
3. NEIGHBORHOOD: What neighborhood or area is mentioned?
4. MIN_RATING: What minimum rating is mentioned? (extract number)
5. BUDGET: What price range is mentioned? (budget, moderate, expensive)

Return as JSON with keys: cuisine (array), vibes (array), neighborhood, min_rating, budget.
If something isn't mentioned, use null. Return ONLY the JSON, no other text."""

        response = await self.client.chat_completion([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ], temperature=0.1)

        import json
        # Handle markdown-formatted JSON response
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        if response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        data = json.loads(response)

        return SearchFilters(
            cuisine=data.get("cuisine"),
            vibes=data.get("vibes"),
            neighborhood=data.get("neighborhood"),
            min_rating=data.get("min_rating"),
            budget=data.get("budget"),
        )


async def parse_and_search(
    query: str,
    search_service: Optional[SearchService] = None,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Parse query and perform search in one step.

    Args:
        query: Natural language query
        search_service: Optional SearchService instance
        limit: Max results

    Returns:
        List of matching restaurants
    """
    search_service = search_service or SearchService()
    parser = QueryParser()

    # Parse query
    filters = await parser.parse(query)

    # Search
    results = await search_service.hybrid_search(query, filters, limit)

    return results


if __name__ == "__main__":
    import asyncio

    async def test():
        parser = QueryParser()
        filters = await parser.parse("Korean food in Brooklyn that's good for a date night")
        print(f"Cuisine: {filters.cuisine}")
        print(f"Vibes: {filters.vibes}")
        print(f"Neighborhood: {filters.neighborhood}")

    asyncio.run(test())
