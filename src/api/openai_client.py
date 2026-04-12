"""
OpenAI client for embeddings and chat completions.
"""

import os
from typing import Optional, List
from openai import OpenAI, AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")


class OpenAIClient:
    """Wrapper for OpenAI API calls."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or OPENAI_API_KEY)

    async def get_embedding(self, text: str) -> List[float]:
        """
        Get text embedding using text-embedding-3-small.

        Args:
            text: Text to embed

        Returns:
            1536-dimensional embedding vector
        """
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

    async def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """
        Get embeddings for multiple texts.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [data.embedding for data in response.data]

    async def chat_completion(
        self,
        messages: List[dict],
        model: str = "gpt-4o-mini",
        temperature: float = 0.3,
        max_tokens: Optional[int] = None
    ) -> str:
        """
        Get chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model to use
            temperature: Response creativity (0-1)
            max_tokens: Max tokens in response

        Returns:
            Assistant response text
        """
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            params["max_tokens"] = max_tokens

        response = await self.client.chat.completions.create(**params)
        return response.choices[0].message.content


# Synchronous wrapper for simpler use cases
class SyncOpenAIClient:
    """Synchronous OpenAI client."""

    def __init__(self, api_key: Optional[str] = None):
        self.client = OpenAI(api_key=api_key or OPENAI_API_KEY)

    def get_embedding(self, text: str) -> List[float]:
        """Get embedding synchronously."""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text
        )
        return response.data[0].embedding

    def get_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Get embeddings for multiple texts synchronously."""
        response = self.client.embeddings.create(
            model="text-embedding-3-small",
            input=texts
        )
        return [data.embedding for data in response.data]

    def chat_completion(
        self,
        messages: List[dict],
        model: str = "gpt-4o-mini",
        temperature: float = 0.3
    ) -> str:
        """Get chat completion synchronously."""
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature
        )
        return response.choices[0].message.content


if __name__ == "__main__":
    import asyncio

    async def test():
        client = OpenAIClient()
        # Test embedding
        embedding = await client.get_embedding("Korean BBQ restaurant")
        print(f"Embedding dimensions: {len(embedding)}")

        # Test chat
        response = await client.chat_completion([
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"}
        ])
        print(f"Response: {response}")

    asyncio.run(test())
