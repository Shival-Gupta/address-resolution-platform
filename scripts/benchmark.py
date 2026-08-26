# File: scripts/benchmark.py
"""Benchmark evaluation script for Address Resolution Platform search tiers.

Compares retrieval methods (Greedy exact, Levenshtein, Tier 1 Lexical, Tier 2 Semantic)
against the synthetic Indian address permutation test suite.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import click
import duckdb
import numpy as np
from tabulate import tabulate

from app.db.repository import AddressRepository
from app.engines.lexical import search as lexical_search
from app.engines.normalizer import normalize
from app.engines.semantic import search as semantic_search


def run_benchmark(
    fixtures_path: str = "./tests/fixtures/permutations.json",
    db_path: str = "./data/addresses.db",
    max_samples: int = 500,
) -> list[dict[str, str | float]]:
    """Run comparative benchmark across address resolution algorithms.

    Args:
        fixtures_path: Path to JSON permutations fixture file.
        db_path: Path to DuckDB database file.
        max_samples: Maximum number of permutations to evaluate.

    Returns:
        list[dict[str, str | float]]: Benchmark metrics per engine.
    """
    fix_file = Path(fixtures_path)
    if not fix_file.exists():
        raise FileNotFoundError(f"Fixture file not found at {fixtures_path}")

    with open(fix_file, encoding="utf-8") as f:
        permutations: list[dict[str, str]] = json.load(f)

    if max_samples and len(permutations) > max_samples:
        permutations = permutations[:max_samples]

    conn = duckdb.connect(db_path, read_only=True)
    repo = AddressRepository()

    # Pre-cache database candidate pool per pincode for speed
    pincode_cache: dict[str, list[dict[str, object]]] = {}

    def get_cached_pool(pin: str | None) -> list[dict[str, object]]:
        key = pin or "ALL"
        if key not in pincode_cache:
            pincode_cache[key] = repo.get_candidate_pool(conn, pincode=pin, limit=5000)
        return pincode_cache[key]

    # Evaluate Tier 1 (Lexical)
    t1_correct = 0
    t1_latencies: list[float] = []

    for item in permutations:
        raw_text = item["input"]
        expected_id = item["expected_sap_id"]

        start = time.perf_counter()
        slots = normalize(raw_text)
        pool = get_cached_pool(slots.pincode)
        matches = lexical_search(slots, pool, top_k=1)
        latency = (time.perf_counter() - start) * 1000.0
        t1_latencies.append(latency)

        if matches and matches[0].sap_premise_id == expected_id:
            t1_correct += 1

    # Evaluate Tier 1 + Tier 2 (Semantic with Number Guardrail)
    t2_correct = 0
    t2_latencies: list[float] = []

    for item in permutations:
        raw_text = item["input"]
        expected_id = item["expected_sap_id"]

        start = time.perf_counter()
        slots = normalize(raw_text)
        pool = get_cached_pool(slots.pincode)

        t1_matches = lexical_search(slots, pool, top_k=5)
        # If Tier 1 confidence satisfies threshold, resolve immediately
        if t1_matches and t1_matches[0].confidence_score >= 0.92:
            resolved_id = t1_matches[0].sap_premise_id
        else:
            t2_matches = semantic_search(slots, pool, top_k=1)
            resolved_id = (
                t2_matches[0].sap_premise_id
                if t2_matches
                else (t1_matches[0].sap_premise_id if t1_matches else None)
            )

        latency = (time.perf_counter() - start) * 1000.0
        t2_latencies.append(latency)

        if resolved_id == expected_id:
            t2_correct += 1

    # Evaluate Greedy Exact Match (lower-cased exact string comparison)
    greedy_correct = 0
    greedy_latencies: list[float] = []
    for item in permutations:
        raw_text = item["input"]
        expected_id = item["expected_sap_id"]
        start = time.perf_counter()
        slots = normalize(raw_text)
        pool = get_cached_pool(slots.pincode)
        query_norm = " ".join(slots.normalized_tokens)
        match_id: str | None = None
        for cand in pool:
            if str(cand.get("normalized_str", "")).strip().lower() == query_norm:
                match_id = str(cand["sap_premise_id"])
                break
        latency = (time.perf_counter() - start) * 1000.0
        greedy_latencies.append(latency)
        if match_id == expected_id:
            greedy_correct += 1

    # Evaluate Vanilla Levenshtein (difflib SequenceMatcher, no token reordering)
    import difflib

    lev_correct = 0
    lev_latencies: list[float] = []
    for item in permutations:
        raw_text = item["input"]
        expected_id = item["expected_sap_id"]
        start = time.perf_counter()
        slots = normalize(raw_text)
        pool = get_cached_pool(slots.pincode)
        query_norm = " ".join(slots.normalized_tokens)
        best_score = 0.0
        best_id: str | None = None
        for cand in pool:
            cand_str = str(cand.get("normalized_str") or cand.get("full_address", ""))
            ratio = difflib.SequenceMatcher(None, query_norm, cand_str.lower()).ratio()
            if ratio > best_score:
                best_score = ratio
                best_id = str(cand["sap_premise_id"])
        latency = (time.perf_counter() - start) * 1000.0
        lev_latencies.append(latency)
        if best_id == expected_id:
            lev_correct += 1

    total = len(permutations)
    conn.close()

    results: list[dict[str, str | float]] = [
        {
            "Method": "Greedy Exact",
            "Accuracy (%)": round((greedy_correct / total) * 100, 2),
            "p50 Latency (ms)": round(float(np.percentile(greedy_latencies, 50)), 2),
            "p95 Latency (ms)": round(float(np.percentile(greedy_latencies, 95)), 2),
            "p99 Latency (ms)": round(float(np.percentile(greedy_latencies, 99)), 2),
        },
        {
            "Method": "Vanilla Levenshtein (difflib)",
            "Accuracy (%)": round((lev_correct / total) * 100, 2),
            "p50 Latency (ms)": round(float(np.percentile(lev_latencies, 50)), 2),
            "p95 Latency (ms)": round(float(np.percentile(lev_latencies, 95)), 2),
            "p99 Latency (ms)": round(float(np.percentile(lev_latencies, 99)), 2),
        },
        {
            "Method": "Tier 1 (Lexical DuckDB + RapidFuzz)",
            "Accuracy (%)": round((t1_correct / total) * 100, 2),
            "p50 Latency (ms)": round(float(np.percentile(t1_latencies, 50)), 2),
            "p95 Latency (ms)": round(float(np.percentile(t1_latencies, 95)), 2),
            "p99 Latency (ms)": round(float(np.percentile(t1_latencies, 99)), 2),
        },
        {
            "Method": "Tier 1 + Tier 2 (Lexical + Semantic)",
            "Accuracy (%)": round((t2_correct / total) * 100, 2),
            "p50 Latency (ms)": round(float(np.percentile(t2_latencies, 50)), 2),
            "p95 Latency (ms)": round(float(np.percentile(t2_latencies, 95)), 2),
            "p99 Latency (ms)": round(float(np.percentile(t2_latencies, 99)), 2),
        },
    ]

    return results


@click.command()
@click.option(
    "--fixtures-path",
    default="./tests/fixtures/permutations.json",
    help="Path to permutations fixture.",
)
@click.option("--db-path", default="./data/addresses.db", help="Path to DuckDB database.")
@click.option("--samples", default=500, help="Number of sample permutations to test.")
@click.option(
    "--output",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    help="Output format.",
)
def cli(fixtures_path: str, db_path: str, samples: int, output: str) -> None:
    """CLI to evaluate search engine benchmark metrics."""
    results = run_benchmark(fixtures_path=fixtures_path, db_path=db_path, max_samples=samples)

    if output == "table":
        click.echo("\n" + tabulate(results, headers="keys", tablefmt="github") + "\n")
    elif output == "json":
        click.echo(json.dumps(results, indent=2))
    elif output == "csv":
        import pandas as pd

        df = pd.DataFrame(results)
        click.echo(df.to_csv(index=False))


if __name__ == "__main__":
    cli()
