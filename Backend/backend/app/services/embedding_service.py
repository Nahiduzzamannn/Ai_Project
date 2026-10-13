"""
Embedding Service for generating OpenAI embeddings.

This module handles all interactions with the OpenAI API for text embeddings.
It uses the text-embedding-3-small model which produces 1536-dimensional vectors.

IMPORTANT: Uses lazy client creation (creates client on each call) to avoid 
import-time crashes if OPENAI_API_KEY is missing. This makes the app more robust.
"""

import os
from openai import OpenAI
from dotenv import load_dotenv, find_dotenv

# Load environment variables (safe redundancy - ensures API key is available)
load_dotenv(find_dotenv())

# Model configuration
EMBED_MODEL = "text-embedding-3-small"  # Produces 1536-dimensional embeddings


def generate_embedding(text: str) -> list[float]:
    """
    Generate an embedding vector for the given text using OpenAI's API.
    
    Uses lazy client creation - creates a new OpenAI client on each call.
    This prevents import-time failures if OPENAI_API_KEY is not set.
    
    Args:
        text: The input text to embed. Should be non-empty.
        
    Returns:
        A list of 1536 floating-point numbers representing the text embedding.
        Returns empty list if text is empty.
        
    Raises:
        RuntimeError: If OPENAI_API_KEY is not set in environment
        OpenAI API errors: If the request fails (auth, rate limit, etc.)
    
    Example:
        >>> embedding = generate_embedding("Machine learning is fascinating")
        >>> len(embedding)
        1536
    """
    # Clean and validate input
    text = (text or "").strip()
    if not text:
        return []
    
    # Check for API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY not found. Put it in Backend\\backend\\.env or set env var."
        )
    
    # Create client (lazy initialization - only when function is called)
    client = OpenAI(api_key=api_key)
    
    # Call OpenAI API to generate embedding
    resp = client.embeddings.create(
        model=EMBED_MODEL,
        input=text
    )
    
    # Extract and return the embedding vector
    return resp.data[0].embedding