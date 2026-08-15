"""Scored evaluation harness. Run with `uv run python -m newsroom_fleet.evaluation`."""

from newsroom_fleet.evaluation.runner import Report, render, run_evaluation

__all__ = ["Report", "render", "run_evaluation"]
