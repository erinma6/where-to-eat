# Where Should You Eat With Erin?

A personal restaurant recommendation chatbot built on Erin's curated Google Maps list. Ask naturally — it uses hybrid semantic + structured search to find the right spot.

## How it works

- **~500 restaurants** from a personal Google Maps saved list
- **Natural language queries** parsed by GPT-4o-mini into structured filters (cuisine, vibe, neighborhood, rating)
- **Hybrid search** combining vector similarity (OpenAI embeddings) with structured filters in Supabase pgvector
- **Results ranked** by 60% semantic relevance + 40% rating
- **Weekly sync** via GitHub Actions keeps the list up to date

## Stack

| Layer | Technology |
|---|---|
| Frontend | Streamlit |
| Database | Supabase (Postgres + pgvector) |
| Embeddings | OpenAI text-embedding-3-small |
| Query parsing | GPT-4o-mini |
| Restaurant data | Google Places API |
| Sync | GitHub Actions (weekly cron) |


## Example queries

- "Korean in Brooklyn"
- "Italian for date night"
- "Casual spots in the West Village"
- "Give me 10 options for brunch"
- "Tell me more about [restaurant name]"

## Project structure

```
app/                  # Streamlit chatbot
src/
  api/                # OpenAI client
  db/                 # Supabase client + repository
  services/           # Hybrid search + query parser
scripts/
  scrape_places.py    # Playwright scraper for Google Maps list
  sync_places.py      # Weekly sync: upsert new, delete removed
supabase/
  schema.sql          # Database schema + hybrid_search function
  generate_embeddings.py
```
