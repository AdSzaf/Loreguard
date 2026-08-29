import hashlib
import math
import re


class EmbeddingProvider:
    """
    Abstract embedding provider (mirrors the plan's LLMProvider
    interface pattern -- swap the implementation, nothing else in
    the app changes). Vectors must be L2-normalized so cosine
    similarity reduces to a plain dot product.
    """

    dimensions: int

    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbeddingProvider(EmbeddingProvider):
    """
    Deterministic, offline, zero-dependency placeholder embedding
    (a hashing-trick bag-of-words vectorizer, similar in spirit to
    scikit-learn's HashingVectorizer).

    This is NOT a semantic embedding -- it has no notion of meaning
    or synonyms, only shared vocabulary. Two notes about "Aldren"
    will score some similarity; a note about "the moon goddess" and
    one about "the lunar deity" will not, despite meaning the same
    thing. It exists purely so the embeddings/similarity pipeline
    is wired up, testable, and usable offline without any API key.

    Swap in a real provider (OpenAI, Voyage, local
    sentence-transformers, etc.) by implementing EmbeddingProvider
    and passing it into EmbeddingService -- everything downstream
    (storage, cosine search, the /similar endpoint) stays the same.
    Changing `dimensions` when swapping providers requires
    re-embedding all documents (old and new vectors aren't
    comparable), which EmbeddingService.reembed_all() does.
    """

    dimensions = 384

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        tokens = re.findall(r"\w+", text.lower(), re.UNICODE)

        for token in tokens:
            bucket = self._bucket(token)
            vector[bucket] += self._sign(token)

        norm = math.sqrt(sum(component * component for component in vector))

        if norm > 0:
            vector = [component / norm for component in vector]

        return vector

    def _bucket(self, token: str) -> int:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return int(digest, 16) % self.dimensions

    def _sign(self, token: str) -> float:
        digest = hashlib.sha256((token + ":sign").encode("utf-8")).hexdigest()
        return 1.0 if int(digest, 16) % 2 == 0 else -1.0


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Real semantic embeddings via Google's Gemini Embedding API
    (gemini-embedding-001). Unlike HashingEmbeddingProvider, this
    actually understands meaning -- "bogini księżyca" and "lunar
    deity" score high similarity here, whereas the hashing provider
    would see them as completely unrelated (zero shared vocabulary).

    Uses Matryoshka Representation Learning (MRL) to request a
    smaller-than-default output size (768 instead of the 3072
    default) -- plenty of resolution for document-similarity search
    at this vault's scale, at a quarter of the storage/compute cost.
    """

    dimensions = 768

    def __init__(self, api_key: str, model: str = "gemini-embedding-001"):
        # Imported lazily so the `google-genai` package is only
        # required when this provider is actually used.
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    def embed(self, text: str) -> list[float]:
        text = text.strip()

        if not text:
            return [0.0] * self.dimensions

        from google.genai import types

        response = self.client.models.embed_content(
            model=self.model,
            contents=text,
            config=types.EmbedContentConfig(
                output_dimensionality=self.dimensions,
            ),
        )

        return list(response.embeddings[0].values)


def get_embedding_provider(settings) -> EmbeddingProvider:
    """
    Picks a real embedding provider if one is configured, falling
    back to the offline hashing placeholder otherwise -- mirrors
    llm_provider.get_llm_provider()'s pattern, so the app never
    hard-fails just because a key isn't set, it just degrades to
    "vocabulary overlap" similarity instead of true semantic search.
    """

    if settings.gemini_api_key:
        return GeminiEmbeddingProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_embedding_model,
        )

    return HashingEmbeddingProvider()
