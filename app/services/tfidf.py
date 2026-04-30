"""
tfidf.py — lightweight TF-IDF scorer used to rank news articles and learn-topic
recommendations by relevance to a user query or interest profile.

No external dependencies — just the standard library + math.
"""

import math
import re
from collections import Counter

# Common English words that carry no topical signal; suppressed during scoring.
STOPWORDS = {
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of",
    "is", "are", "was", "were", "be", "been", "being", "it", "this", "that",
    "with", "by", "from", "as", "not", "but", "he", "she", "we", "they",
    "i", "you", "my", "your", "our", "its", "their", "which", "who", "what",
    "how", "when", "where", "if", "then", "so", "than", "into", "about",
    "up", "out", "more", "also", "can", "will", "has", "have", "had",
    "do", "does", "did", "all", "any", "some", "no", "new", "over",
}


def _tokenize(text: str) -> list:
    """Lower-case, strip punctuation, split on whitespace, remove stopwords."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if t not in STOPWORDS]


def tfidf_scores(query: str, documents: list) -> list:
    """
    Return a TF-IDF relevance score for each document in *documents*
    given the *query* string.

    Uses smoothed IDF:  idf(t) = log((N+1) / (df(t)+1)) + 1
    so that unseen terms don't cause division-by-zero and every term
    gets at least a small weight even when df == N.

    Parameters
    ----------
    query : str
        The search / interest-profile string.
    documents : list[str]
        Corpus to rank.

    Returns
    -------
    list[float]
        One score per document (same order as *documents*).
        Higher score = more relevant.
    """
    query_terms = _tokenize(query)
    if not query_terms or not documents:
        return [0.0] * len(documents)

    N = len(documents)
    tokenized = [_tokenize(d) for d in documents]

    scores = []
    for tokens in tokenized:
        if not tokens:
            scores.append(0.0)
            continue

        tf_map = Counter(tokens)
        doc_len = len(tokens)
        score = 0.0

        for term in query_terms:
            # term frequency: normalised by document length
            tf = tf_map[term] / doc_len
            # document frequency: how many docs contain this term
            df = sum(1 for td in tokenized if term in td)
            # smoothed IDF keeps scores finite even when df == 0 or df == N
            idf = math.log((N + 1) / (df + 1)) + 1.0
            score += tf * idf

        scores.append(score)

    return scores


def rank_documents(query: str, documents: list) -> list:
    """
    Return documents sorted by descending TF-IDF relevance to *query*.

    Each element of the returned list is a dict:
        {"document": <original str>, "score": <float>}
    """
    scores = tfidf_scores(query, documents)
    ranked = sorted(
        zip(documents, scores),
        key=lambda pair: pair[1],
        reverse=True,
    )
    return [{"document": doc, "score": score} for doc, score in ranked]
