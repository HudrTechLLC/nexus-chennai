"""Linking evaluation vs the rules-only baseline (spec F3). Run with `python -m app.eval`."""

from .core import Evaluator, Truth, load_truth, pair_metrics, series_purity

__all__ = ["Evaluator", "Truth", "load_truth", "pair_metrics", "series_purity"]
