"""
Generate embeddings for restaurants in Supabase.

This script:
1. Fetches all restaurants without embeddings
2. Generates embeddings using OpenAI (text-embedding-3-small)
3. Updates the records in Supabase
"""

import os
import sys
import asyncio
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.supabase_client import get_client, RestaurantRepository
from src.api.openai_client import SyncOpenAIClient

load_dotenv()


def create_embedding_text(restaurant: Dict[str, Any]) -> str:
    """Create text representation of a restaurant for embedding."""
    parts = [
        restaurant.get("name", ""),
        restaurant.get("address", ""),
        restaurant.get("neighborhood", ""),
    ]

    # Add cuisine tags if available
    if restaurant.get("cuisine_tags"):
        parts.extend(restaurant["cuisine_tags"])

    # Add vibe tags if available
    if restaurant.get("vibe_tags"):
        parts.extend(restaurant["vibe_tags"])

    # Add notes if available
    if restaurant.get("notes"):
        parts.append(restaurant["notes"])

    # Filter out empty strings and join
    return ", ".join([p for p in parts if p])


def generate_embeddings_batch(
    client: SyncOpenAIClient,
    texts: List[str],
    batch_size: int = 100
) -> List[List[float]]:
    """Generate embeddings in batches."""
    all_embeddings = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        print(f"  Processing batch {i // batch_size + 1}/{(len(texts) + batch_size - 1) // batch_size}...")
        embeddings = client.get_embeddings(batch)
        all_embeddings.extend(embeddings)

    return all_embeddings


def update_embeddings_in_supabase(
    repo: RestaurantRepository,
    restaurants: List[Dict[str, Any]],
    embeddings: List[List[float]]
) -> int:
    """Update restaurants with their embeddings."""
    updated = 0

    for restaurant, embedding in zip(restaurants, embeddings):
        try:
            repo.table.update({
                "embedding": embedding,
                "updated_at": "now()"
            }).eq("id", restaurant["id"]).execute()
            updated += 1
        except Exception as e:
            print(f"  Error updating {restaurant.get('name')}: {e}")

    return updated


def main():
    """Main function to generate embeddings."""
    print("=" * 60)
    print("Restaurant Embedding Generator")
    print("=" * 60)

    # Initialize clients
    print("\n1. Connecting to Supabase...")
    repo = RestaurantRepository()
    total = repo.count()
    print(f"   Total restaurants in database: {total}")

    # Get all restaurants
    print("\n2. Fetching all restaurants...")
    all_restaurants = repo.get_all(limit=total)
    print(f"   Fetched {len(all_restaurants)} restaurants")

    # Check which ones need embeddings
    restaurants_needing_embeddings = [
        r for r in all_restaurants
        if r.get("embedding") is None
    ]
    print(f"   Restaurants needing embeddings: {len(restaurants_needing_embeddings)}")

    if len(restaurants_needing_embeddings) == 0:
        print("\n✓ All restaurants already have embeddings!")
        return

    # Create text for embedding
    print("\n3. Creating text representations...")
    texts = [create_embedding_text(r) for r in restaurants_needing_embeddings]

    # Show sample
    print("   Sample text for embedding:")
    print(f"   '{texts[0][:100]}...'")

    # Generate embeddings
    print("\n4. Generating embeddings with OpenAI (text-embedding-3-small)...")
    openai_client = SyncOpenAIClient()

    # Process in batches
    embeddings = generate_embeddings_batch(openai_client, texts, batch_size=100)
    print(f"   Generated {len(embeddings)} embeddings")

    # Update Supabase
    print("\n5. Updating Supabase with embeddings...")
    updated = update_embeddings_in_supabase(
        repo,
        restaurants_needing_embeddings,
        embeddings
    )
    print(f"   Updated {updated} restaurants")

    print("\n" + "=" * 60)
    print("✓ Embedding generation complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
