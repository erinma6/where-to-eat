-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Restaurants table
CREATE TABLE restaurants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    google_place_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    address TEXT,
    neighborhood TEXT,
    latitude DECIMAL(10, 8),
    longitude DECIMAL(11, 8),
    rating DECIMAL(2, 1),
    total_ratings INTEGER DEFAULT 0,
    price_level INTEGER CHECK (price_level BETWEEN 1 AND 4),
    cuisine_tags TEXT[],  -- Array of cuisine types: ['Korean', 'BBQ']
    vibe_tags TEXT[],     -- Array of vibes: ['casual', 'date night', 'lively']
    notes TEXT,           -- AI-generated summary of reviews
    personal_notes TEXT,  -- User's own notes
    embedding VECTOR(1536),  -- OpenAI text-embedding-3-small
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient querying
CREATE INDEX idx_restaurants_cuisine ON restaurants USING GIN (cuisine_tags);
CREATE INDEX idx_restaurants_vibes ON restaurants USING GIN (vibe_tags);
CREATE INDEX idx_restaurants_neighborhood ON restaurants (neighborhood);
CREATE INDEX idx_restaurants_rating ON restaurants (rating DESC);

-- Hybrid search: combine text search with vector similarity
-- This function returns restaurants matching structured filters + semantic search
CREATE OR REPLACE FUNCTION hybrid_search(
    query_embedding VECTOR(1536),
    query_cuisine TEXT[],
    query_vibes TEXT[],
    query_neighborhood TEXT,
    min_rating DECIMAL(2, 1),
    limit_count INTEGER DEFAULT 10
)
RETURNS TABLE (
    id UUID,
    name TEXT,
    address TEXT,
    neighborhood TEXT,
    rating DECIMAL(2, 1),
    cuisine_tags TEXT[],
    vibe_tags TEXT[],
    notes TEXT,
    similarity DOUBLE PRECISION
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        r.id,
        r.name,
        r.address,
        r.neighborhood,
        r.rating,
        r.cuisine_tags,
        r.vibe_tags,
        r.notes,
        (
            -- Vector similarity score (1 = perfect match)
            1 - (r.embedding <=> query_embedding)
        ) AS similarity
    FROM restaurants r
    WHERE
        (query_cuisine IS NULL OR r.cuisine_tags && query_cuisine)
        AND (query_vibes IS NULL OR r.vibe_tags && query_vibes)
        AND (query_neighborhood IS NULL OR LOWER(r.neighborhood) = LOWER(query_neighborhood))
        AND (min_rating IS NULL OR r.rating >= min_rating)
    ORDER BY similarity DESC
    LIMIT limit_count;
END;
$$;
