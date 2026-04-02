"""Tests for scout.cli — CLI invocation and output format."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

_FIXTURES = Path(__file__).parent / "fixtures" / "sample_listings.json"

# A minimal listing file with one good listing and one bad one.
# Listings are separated by double blank lines (single blank lines are
# internal to a listing — e.g., between title and description).
_SAMPLE_FILE_CONTENT = """\
Fix TypeError in checkout flow

Our Stripe checkout is throwing a TypeError on line 42 of checkout.js
when the cart has more than 10 items. Repo access provided.

Budget: $350
Skills: JavaScript, React, Stripe
Client spent $4,500
Hire rate: 78%


Build my app like Uber for dog walkers

I have an idea for a two-sided marketplace.
Build my app from scratch. Full-stack developer needed.

Budget: $2,000
Skills: React Native, Node.js
Client spent $1,200
Hire rate: 65%
"""

# Very short listing that will parse as LOW confidence
_VAGUE_LISTING = "need help with website\n"


def _run_cli(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    """Run scout CLI via subprocess."""
    cmd = [sys.executable, "-m", "scout", *args]
    return subprocess.run(
        cmd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(Path(__file__).parents[1]),
    )


class TestScoreSubcommand:
    """Tests for the 'score' subcommand."""

    def test_file_flag(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name)
        assert result.returncode == 0
        assert "SCOUT RESULTS" in result.stdout

    def test_stdin_input(self) -> None:
        result = _run_cli("score", stdin=_SAMPLE_FILE_CONTENT)
        assert result.returncode == 0
        assert "SCOUT RESULTS" in result.stdout

    def test_json_flag_valid_json(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name, "--json")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "ranked" in data
        assert "rejected" in data
        assert "needs_review" in data
        assert "stats" in data

    def test_json_has_stats_fields(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name, "--json")
        data = json.loads(result.stdout)
        stats = data["stats"]
        assert "total_parsed" in stats
        assert "passed_gates" in stats
        assert "confidence_distribution" in stats

    def test_top_flag(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name, "--top", "1")
        assert result.returncode == 0
        # Should still say "SCOUT RESULTS"
        assert "SCOUT RESULTS" in result.stdout

    def test_platform_flag(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name, "--platform", "upwork")
        assert result.returncode == 0

    def test_empty_input_exits_nonzero(self) -> None:
        result = _run_cli("score", stdin="")
        assert result.returncode != 0

    def test_human_output_has_rejected_section(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name)
        # MVP listing should be rejected
        assert "REJECTED" in result.stdout

    def test_human_output_has_pipeline_footer(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name)
        assert "Pipeline:" in result.stdout
        assert "listings processed" in result.stdout

    def test_no_llm_scores_note(self) -> None:
        """Without pre_scores, CLI should show the gate-filtering note."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name)
        assert "gate filtering only" in result.stdout


class TestNormalizeSubcommand:
    """Tests for the 'normalize' subcommand (placeholder)."""

    def test_normalize_prints_placeholder(self) -> None:
        result = _run_cli("normalize", "1")
        assert result.returncode == 0
        assert "PRJ-371" in result.stdout
        assert "Not yet implemented" in result.stdout


class TestNoSubcommand:
    """Test behavior with no subcommand."""

    def test_no_command_shows_help(self) -> None:
        result = _run_cli()
        assert result.returncode != 0


class TestJsonOutputStructure:
    """Verify JSON output matches expected schema."""

    def test_ranked_entry_has_required_fields(self) -> None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(_SAMPLE_FILE_CONTENT)
            f.flush()
            result = _run_cli("score", "--file", f.name, "--json")
        data = json.loads(result.stdout)
        # At least one entry should exist (bug fix listing passes gates)
        all_entries = data["ranked"] + data["rejected"] + data["needs_review"]
        assert len(all_entries) > 0
        for entry in all_entries:
            assert "title" in entry
            assert "platform" in entry
            assert "total_score" in entry
            assert "gate_results" in entry
