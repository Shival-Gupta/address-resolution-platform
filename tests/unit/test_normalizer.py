# File: tests/unit/test_normalizer.py
"""Unit tests for Tier 0 Normalizer engine.

Validates Indian address abbreviation expansion, slot extraction (pincode, premise,
flat, street, landmark, city, state), number-blindness guardrails, and error handling.
"""

from __future__ import annotations

import pytest

from app.core.exceptions import NormalizationError
from app.engines.normalizer import (
    extract_pincode,
    normalize,
)


class TestNormalizerPermutations:
    """Test standard permutation cases specified in architecture and implementation plan."""

    @pytest.mark.parametrize(
        "raw_input",
        [
            "#7-B, 42, M. Gandhi Rd., Patna (800001)",
            "Flat 7B, 42 Gandhi Rd., 800001 Patna",
            "42 MG Rd, #7B, Patna, BR 800001, IN",
            "7B - 42 MG Road, Patna 800001, Bihar",
            "42/7B MG Rd, Patna-800001",
        ],
    )
    def test_patna_permutations_resolve_to_same_slots(self, raw_input: str) -> None:
        """Verify all syntactic variations of base address produce identical core slots."""
        slots = normalize(raw_input)
        assert slots.pincode == "800001"
        assert slots.pincode_missing is False
        assert slots.premise_number == "42"
        assert slots.flat_no == "7b"
        assert slots.city == "patna"
        assert "mahatma gandhi road" in (slots.street or "")


class TestAbbreviationExpansion:
    """Test expansion of street, subpremise, and Indian geographical abbreviations."""

    @pytest.mark.parametrize(
        ("input_street", "expected_contains"),
        [
            ("42 M.G. Rd, Patna 800001", "mahatma gandhi road"),
            ("42 MG Rd, Patna 800001", "mahatma gandhi road"),
            ("42 mg rd, patna 800001", "mahatma gandhi road"),
            ("10 J.L.N. Marg, Delhi 110001", "jawaharlal nehru road"),
            ("15 Anna Salai, Chennai 600001", "anna road"),
            ("20 Park St, Kolkata 700001", "park street"),
            ("50 Brigade Ave, Bengaluru 560001", "brigade avenue"),
        ],
    )
    def test_street_abbreviations(self, input_street: str, expected_contains: str) -> None:
        """Test expansion of common street types and Indian road names."""
        slots = normalize(input_street)
        assert slots.street is not None
        assert expected_contains in slots.street

    @pytest.mark.parametrize(
        ("raw_input", "expected_state"),
        [
            ("42 MG Road, Patna, BR 800001", "bihar"),
            ("100 Linking Road, Mumbai, MH 400050", "maharashtra"),
            ("50 Ring Road, Delhi, DL 110001", "delhi"),
            ("12 Indiranagar, Bengaluru, KA 560038", "karnataka"),
            ("25 Park Street, Kolkata, WB 700019", "west bengal"),
            ("5 Mount Road, Chennai, TN 600002", "tamil nadu"),
        ],
    )
    def test_state_abbreviations(self, raw_input: str, expected_state: str) -> None:
        """Test expansion of Indian 2-letter state codes."""
        slots = normalize(raw_input)
        assert slots.state == expected_state


class TestNumberBlindnessGuardrail:
    """Validate that dense embedding guardrail numbers are extracted exactly."""

    def test_flat_7a_vs_flat_7b_distinction(self) -> None:
        """Verify Flat 7A and Flat 7B are distinctly extracted for number filtering."""
        slots_7a = normalize("Flat 7A, 42 Mahatma Gandhi Road, Patna 800001")
        slots_7b = normalize("Flat 7B, 42 Mahatma Gandhi Road, Patna 800001")

        assert slots_7a.flat_no == "7a"
        assert slots_7b.flat_no == "7b"
        assert slots_7a.premise_number == "42"
        assert slots_7b.premise_number == "42"
        assert slots_7a.flat_no != slots_7b.flat_no

    @pytest.mark.parametrize(
        ("subpremise_text", "expected_flat"),
        [
            ("Flat 7B", "7b"),
            ("Fl. 7B", "7b"),
            ("Fl 7B", "7b"),
            ("#7B", "7b"),
            ("#7-B", "7b"),
            ("7/B", "7b"),
            ("Apt 7B", "7b"),
            ("Suite 7B", "7b"),
            ("Unit 7-B", "7b"),
        ],
    )
    def test_subpremise_formats(self, subpremise_text: str, expected_flat: str) -> None:
        """Test normalization of all supported subpremise formatting styles."""
        raw = f"{subpremise_text}, 42 MG Road, Patna 800001"
        slots = normalize(raw)
        assert slots.flat_no == expected_flat
        assert slots.premise_number == "42"


class TestPincodeAndLandmarks:
    """Test pincode detection, missing pincode flags, and landmark slot extraction."""

    def test_valid_pincode_extraction(self) -> None:
        """Test extraction of 6-digit Indian postal code."""
        pincode, text = extract_pincode("42 MG Road Patna 800001 Bihar")
        assert pincode == "800001"
        assert "800001" not in text

    def test_missing_pincode_flagging(self) -> None:
        """Test that address lacking 6-digit PIN has pincode_missing=True."""
        slots = normalize("Flat 7B, 42 Mahatma Gandhi Road, Near Gandhi Maidan, Patna, Bihar")
        assert slots.pincode is None
        assert slots.pincode_missing is True
        assert slots.premise_number == "42"
        assert slots.flat_no == "7b"
        assert slots.city == "patna"
        assert slots.state == "bihar"
        assert slots.landmark is not None
        assert "near gandhi maidan" in slots.landmark

    def test_landmark_extraction(self) -> None:
        """Test landmark detection with near / opposite phrases."""
        slots = normalize("42 MG Road, Near Central Mall, Patna 800001")
        assert slots.landmark is not None
        assert "near central mall" in slots.landmark


class TestNormalizerEdgeCases:
    """Test edge cases, sorting tokens, and error handling."""

    def test_empty_string_raises_normalization_error(self) -> None:
        """Test that empty string raises NormalizationError."""
        with pytest.raises(NormalizationError):
            normalize("")

    def test_whitespace_string_raises_normalization_error(self) -> None:
        """Test that whitespace-only string raises NormalizationError."""
        with pytest.raises(NormalizationError):
            normalize("    ")

    def test_normalized_tokens_sorted_and_deduplicated(self) -> None:
        """Test that normalized_tokens is alphabetically sorted and deduplicated."""
        slots = normalize("Flat 7B, 42 MG Road, Patna 800001")
        assert slots.normalized_tokens == sorted(slots.normalized_tokens)
        assert len(slots.normalized_tokens) == len(set(slots.normalized_tokens))
        assert "800001" in slots.normalized_tokens
        assert "42" in slots.normalized_tokens
        assert "7b" in slots.normalized_tokens
