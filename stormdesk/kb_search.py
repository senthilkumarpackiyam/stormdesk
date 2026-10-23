"""Keyword search over knowledge-base articles (BM25, the classic search-engine ranking formula).

A few dozen short articles don't need a vector database; this is instant, free, and easy to explain."""

import math
import re
from collections import Counter

STOPWORDS = {
    "a", "an", "and", "are", "at", "be", "but", "can", "cannot", "do", "doesn", "don", "for", "from",
    "has", "have", "i", "im", "in", "is", "isn", "it", "its", "just", "me", "my", "of", "on", "or",
    "so", "t", "that", "the", "this", "to", "was", "when", "with", "won", "you", "your",
}


def tokenize(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower().replace("'", "")) if t not in STOPWORDS]


class KBIndex:
    K1 = 1.5
    B = 0.75

    def __init__(self, articles: list[dict]):
        self.articles = articles
        # Titles count twice: they are the strongest signal of what an article is about.
        self.docs = [tokenize(f"{a['title']} {a['title']} {a['keywords']} {a['category']}") for a in articles]
        self.avg_len = sum(map(len, self.docs)) / max(len(self.docs), 1)
        n = len(self.docs)
        df = Counter(t for doc in self.docs for t in set(doc))
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def search(self, query: str, k: int = 2, min_score: float = 1.5) -> list[dict]:
        terms = tokenize(query)
        scored = []
        for article, doc in zip(self.articles, self.docs):
            tf = Counter(doc)
            score = 0.0
            for t in terms:
                if t in tf:
                    norm = 1 - self.B + self.B * len(doc) / self.avg_len
                    score += self.idf[t] * tf[t] * (self.K1 + 1) / (tf[t] + self.K1 * norm)
            if score >= min_score:
                scored.append((score, article))
        scored.sort(key=lambda pair: -pair[0])
        return [article for _, article in scored[:k]]
