# File: app/engines/normalizer.py
"""Tier 0 Normalizer Engine for unstructured Indian addresses.

Provides deterministic slot extraction (pincode, premise, flat, street, landmark,
city, state, country) and sorted token normalization. Implements the Number-Blindness
guardrail by isolating premise and sub-premise numbers before downstream search.
"""

from __future__ import annotations

import re
from typing import Final

from app.core.exceptions import NormalizationError
from app.models.address import AddressSlots

# Pincode regex: 6 digits, first digit 1-9
PINCODE_PATTERN: Final[re.Pattern[str]] = re.compile(r"\b([1-9][0-9]{5})\b")

# Abbreviation Dictionary
ABBREVIATIONS: Final[dict[str, str]] = {
    # Street types
    "rd": "road",
    "st": "street",
    "ave": "avenue",
    "av": "avenue",
    "blvd": "boulevard",
    "ln": "lane",
    "dr": "drive",
    "marg": "road",
    "mrg": "road",
    "salai": "road",
    "rasta": "road",
    "path": "road",
    "chowk": "chowk",
    "cross": "cross",
    # Sub-premises
    "fl": "flat",
    "apt": "flat",
    "apartment": "flat",
    "ste": "flat",
    "suite": "flat",
    "unit": "flat",
    "blk": "block",
    "block": "block",
    # Indian names & prefixes
    "mg": "mahatma gandhi",
    "m g": "mahatma gandhi",
    "jl": "jawaharlal",
    "j l": "jawaharlal",
    "jln": "jawaharlal nehru",
    "j l n": "jawaharlal nehru",
    "nr": "near",
    "nrby": "near",
    "opp": "opposite",
    "oppo": "opposite",
    "adj": "adjacent",
    "bh": "behind",
    # States
    "br": "bihar",
    "mh": "maharashtra",
    "dl": "delhi",
    "ncr": "delhi",
    "ka": "karnataka",
    "wb": "west bengal",
    "tn": "tamil nadu",
    "up": "uttar pradesh",
    "gj": "gujarat",
    "rj": "rajasthan",
    "mp": "madhya pradesh",
    "ts": "telangana",
    "tg": "telangana",
    "ap": "andhra pradesh",
    "kl": "kerala",
    "hr": "haryana",
    "pb": "punjab",
    "uk": "uttarakhand",
    "jh": "jharkhand",
    "or": "odisha",
    "od": "odisha",
    "as": "assam",
    "ga": "goa",
    # Country
    "in": "india",
    "ind": "india",
    "bharat": "india",
}

# Known Indian Cities mapped to their State
CITY_STATE_MAP: Final[dict[str, str]] = {
    "new delhi": "delhi",
    "patna": "bihar",
    "gaya": "bihar",
    "muzaffarpur": "bihar",
    "bhagalpur": "bihar",
    "mumbai": "maharashtra",
    "pune": "maharashtra",
    "nagpur": "maharashtra",
    "nashik": "maharashtra",
    "bengaluru": "karnataka",
    "bangalore": "karnataka",
    "mysuru": "karnataka",
    "mysore": "karnataka",
    "delhi": "delhi",
    "kolkata": "west bengal",
    "calcutta": "west bengal",
    "howrah": "west bengal",
    "chennai": "tamil nadu",
    "madras": "tamil nadu",
    "coimbatore": "tamil nadu",
    "madurai": "tamil nadu",
    "hyderabad": "telangana",
    "secunderabad": "telangana",
    "ahmedabad": "gujarat",
    "surat": "gujarat",
    "vadodara": "gujarat",
    "jaipur": "rajasthan",
    "jodhpur": "rajasthan",
    "udaipur": "rajasthan",
    "lucknow": "uttar pradesh",
    "kanpur": "uttar pradesh",
    "varanasi": "uttar pradesh",
    "noida": "uttar pradesh",
    "ghaziabad": "uttar pradesh",
    "indore": "madhya pradesh",
    "bhopal": "madhya pradesh",
    "chandigarh": "punjab",
    "ludhiana": "punjab",
    "amritsar": "punjab",
    "gurgaon": "haryana",
    "gurugram": "haryana",
    "kochi": "kerala",
    "cochin": "kerala",
    "thiruvananthapuram": "kerala",
    "trivandrum": "kerala",
    "visakhapatnam": "andhra pradesh",
    "vizag": "andhra pradesh",
    "vijayawada": "andhra pradesh",
    "guwahati": "assam",
    "ranchi": "jharkhand",
    "jamshedpur": "jharkhand",
    "bhubaneswar": "odisha",
    "cuttack": "odisha",
    "dehradun": "uttarakhand",
}

# Known Indian States set
INDIAN_STATES: Final[set[str]] = {
    "bihar",
    "maharashtra",
    "karnataka",
    "delhi",
    "west bengal",
    "tamil nadu",
    "uttar pradesh",
    "gujarat",
    "rajasthan",
    "madhya pradesh",
    "telangana",
    "andhra pradesh",
    "kerala",
    "haryana",
    "punjab",
    "uttarakhand",
    "jharkhand",
    "odisha",
    "assam",
    "goa",
    "himachal pradesh",
    "chhattisgarh",
}


def clean_punctuation(text: str) -> str:
    """Standardize punctuation and clean up abbreviation periods and separators.

    Args:
        text: Raw address string.

    Returns:
        str: Cleaned text with normalized spacing.
    """
    # Remove periods in abbreviations like M.G. -> MG, J.L.N. -> JLN, Rd. -> Rd
    text_clean = re.sub(r"\b([a-zA-Z]{1,5})\.", r"\1", text)
    # Double pass for consecutive abbreviations like M.G.
    text_clean = re.sub(r"\b([a-zA-Z]{1,5})\.", r"\1", text_clean)
    # Replace separators with spaces
    text_clean = text_clean.replace("(", " ").replace(")", " ")
    text_clean = text_clean.replace(";", " ").replace(":", " ").replace("&", " and ")
    return " ".join(text_clean.split())


def extract_pincode(text: str) -> tuple[str | None, str]:
    """Extract first 6-digit Indian PIN code and return remaining text.

    Args:
        text: Address text to scan.

    Returns:
        tuple[str | None, str]: (pincode, cleaned_text_without_pincode)
    """
    match = PINCODE_PATTERN.search(text)
    if match:
        pincode = match.group(1)
        text_without_pin = PINCODE_PATTERN.sub(" ", text)
        return pincode, " ".join(text_without_pin.split())
    return None, text


def extract_premise_and_flat(text: str) -> tuple[str | None, str | None, str]:
    """Extract premise number and flat/sub-premise number.

    Args:
        text: Address text to parse.

    Returns:
        tuple[str | None, str | None, str]: (premise_number, flat_no, remaining_text)
    """
    premise_num: str | None = None
    flat_no: str | None = None
    working_text = text

    # Pattern 1: Slash subpremise at start e.g. "7/B, 42 MG Rd" or "7/B 42"
    slash_prefix = re.search(
        r"\b([0-9]{1,4}[a-zA-Z]?)\s*[/]\s*([a-zA-Z]|[0-9]{1,4})\s*[,–-]?\s*(\d{1,4})\b",
        working_text,
    )
    if slash_prefix:
        flat_no = f"{slash_prefix.group(1)}{slash_prefix.group(2)}".lower()
        premise_num = slash_prefix.group(3)
        working_text = (
            working_text[: slash_prefix.start()] + " " + working_text[slash_prefix.end() :]
        )
        return premise_num, flat_no, " ".join(working_text.split())

    # Pattern 2: Premise / Flat combination e.g. "42/7B" or "42/7-B"
    comb_match = re.search(
        r"\b(\d{1,4})\s*[/]\s*([0-9]{1,4}[a-zA-Z]|[a-zA-Z][0-9]{1,4}|\d{1,4}[a-zA-Z]?)\b",
        working_text,
    )
    if comb_match:
        premise_num = comb_match.group(1)
        flat_no = comb_match.group(2).lower().replace("-", "")
        working_text = working_text[: comb_match.start()] + " " + working_text[comb_match.end() :]
        return premise_num, flat_no, " ".join(working_text.split())

    # Pattern 3: Prefix flat order "7B - 42" or "7-B - 42" or "Flat 7B, 42"
    prefix_pattern = (
        r"\b(?:flat\s+|fl\s*|#\s*)?"
        r"(\d{1,4}[a-zA-Z]|\d{1,4}-[a-zA-Z]|[a-zA-Z]\d{1,4})\s*[-–,\s]+\s*(\d{1,4})\b"
    )
    prefix_match = re.search(prefix_pattern, working_text, re.IGNORECASE)
    if prefix_match:
        flat_no = prefix_match.group(1).lower().replace("-", "").replace("#", "")
        premise_num = prefix_match.group(2)
        working_text = (
            working_text[: prefix_match.start()] + " " + working_text[prefix_match.end() :]
        )
        return premise_num, flat_no, " ".join(working_text.split())

    # Pattern 4: Explicit flat with keyword ("Flat 7B", "Fl 7B", "Apt 7B", "#7B", "#7-B", "7/B")
    flat_pattern = (
        r"\b(?:flat|fl|apt|apartment|suite|ste|unit|#)\s*#?"
        r"([0-9]{1,4}[a-zA-Z]?|[a-zA-Z][0-9]{1,4}|[0-9]{1,4}-[a-zA-Z])\b"
    )
    flat_match = re.search(flat_pattern, working_text, re.IGNORECASE)
    if not flat_match:
        standalone_pattern = r"(?:#|(?<=\b))([0-9]{1,4}[a-zA-Z]|\d{1,4}[/-][a-zA-Z])(?=\s*[, ]|\b)"
        flat_match = re.search(standalone_pattern, working_text)

    if flat_match:
        flat_no = flat_match.group(1).lower().replace("-", "").replace("/", "").replace("#", "")
        working_text = working_text[: flat_match.start()] + " " + working_text[flat_match.end() :]

    # Pattern 5: Standalone premise number (1 to 4 digits)
    premise_match = re.search(r"\b(\d{1,4})\b", working_text)
    if premise_match:
        premise_num = premise_match.group(1)
        working_text = (
            working_text[: premise_match.start()] + " " + working_text[premise_match.end() :]
        )

    return premise_num, flat_no, " ".join(working_text.split())


def extract_landmark_clause(text: str) -> tuple[str | None, str]:
    """Extract landmark clause starting with near, opposite, behind, or adjacent.

    Args:
        text: Address text to parse.

    Returns:
        tuple[str | None, str]: (extracted_landmark, text_without_landmark)
    """
    landmark_pattern = r"\b(near|opposite|opp|behind|adjacent(?:\s+to)?)\s+([^,]+)"
    match = re.search(landmark_pattern, text, re.IGNORECASE)
    if match:
        landmark = f"{match.group(1)} {match.group(2).strip()}".lower()
        # Clean trailing state or city if accidentally captured
        for city_name in CITY_STATE_MAP:
            landmark = re.sub(rf"\b{re.escape(city_name)}\b.*$", "", landmark).strip()
        for state_name in INDIAN_STATES:
            landmark = re.sub(rf"\b{re.escape(state_name)}\b.*$", "", landmark).strip()

        remaining_text = text[: match.start()] + " " + text[match.end() :]
        return landmark, " ".join(remaining_text.split())
    return None, text


def expand_tokens(text: str) -> list[str]:
    """Tokenize and expand abbreviations using the domain abbreviation dictionary.

    Args:
        text: Normalized lowercase text string.

    Returns:
        list[str]: Expanded token sequence.
    """
    raw_tokens = (
        text.replace(",", " ")
        .replace(".", " ")
        .replace("-", " ")
        .replace("#", " ")
        .replace("/", " ")
        .split()
    )
    expanded: list[str] = []

    i = 0
    while i < len(raw_tokens):
        token = raw_tokens[i].lower().strip()
        if not token:
            i += 1
            continue

        # Check three-word phrases (e.g. "j l n")
        if i + 2 < len(raw_tokens):
            three_word = (
                f"{token} {raw_tokens[i + 1].lower().strip()} {raw_tokens[i + 2].lower().strip()}"
            )
            if three_word in ABBREVIATIONS:
                expanded.extend(ABBREVIATIONS[three_word].split())
                i += 3
                continue

        # Check two-word phrases (e.g. "m g", "j l", "west bengal", "new delhi")
        if i + 1 < len(raw_tokens):
            two_word = f"{token} {raw_tokens[i + 1].lower().strip()}"
            if two_word in ABBREVIATIONS:
                expanded.extend(ABBREVIATIONS[two_word].split())
                i += 2
                continue

        # Check single-word abbreviation
        if token in ABBREVIATIONS:
            expanded.extend(ABBREVIATIONS[token].split())
        else:
            expanded.append(token)
        i += 1

    return expanded


def extract_locality(
    tokens: list[str],
) -> tuple[str | None, str | None, list[str]]:
    """Extract city, state, and remaining street tokens.

    Args:
        tokens: Expanded token list.

    Returns:
        tuple[str | None, str | None, list[str]]: (city, state, remaining_tokens)
    """
    city: str | None = None
    state: str | None = None
    remaining: list[str] = []

    text = " ".join(tokens)

    # Check multi-word cities and single-word cities
    for known_city, known_state in CITY_STATE_MAP.items():
        if f" {known_city} " in f" {text} ":
            city = known_city
            state = known_state
            text = re.sub(rf"\b{re.escape(known_city)}\b", " ", text)
            break

    # Check multi-word states or single-word states
    if not state:
        for known_state in INDIAN_STATES:
            if f" {known_state} " in f" {text} ":
                state = known_state
                text = re.sub(rf"\b{re.escape(known_state)}\b", " ", text)
                break

    for t in text.split():
        if t in {"india", "in", "bharat"}:
            continue
        if t in (city, state):
            continue
        remaining.append(t)

    return city, state, remaining


def build_street_string(remaining_tokens: list[str]) -> str | None:
    """Build normalized canonical street string from remaining street tokens.

    Args:
        remaining_tokens: Tokens belonging to street description.

    Returns:
        str | None: Joined street string or None if empty.
    """
    if not remaining_tokens:
        return None

    street_text = " ".join(remaining_tokens)
    # Standardize lone "gandhi road" -> "mahatma gandhi road"
    if "gandhi road" in street_text and "mahatma gandhi road" not in street_text:
        street_text = street_text.replace("gandhi road", "mahatma gandhi road")
    if "nehru road" in street_text and "jawaharlal nehru road" not in street_text:
        street_text = street_text.replace("nehru road", "jawaharlal nehru road")

    return " ".join(street_text.split())


def normalize(raw_address: str) -> AddressSlots:
    """Normalize a raw unstructured Indian address into structured AddressSlots.

    Args:
        raw_address: Unstructured input address string.

    Returns:
        AddressSlots: Structured slots with extracted pincode, premise, flat, street, city, state.

    Raises:
        NormalizationError: If raw_address is empty or whitespace only.
    """
    if not raw_address or not raw_address.strip():
        raise NormalizationError("Address string cannot be empty")

    cleaned = clean_punctuation(raw_address.strip())

    # Step 1: Extract 6-digit Pincode
    pincode, text_no_pin = extract_pincode(cleaned)
    pincode_missing = pincode is None

    # Step 2: Extract Premise and Flat Numbers
    premise_num, flat_no, text_no_num = extract_premise_and_flat(text_no_pin)

    # Step 3: Extract Landmark Clause
    landmark, text_no_landmark = extract_landmark_clause(text_no_num)

    # Step 4: Expand abbreviations and token sequence
    tokens = expand_tokens(text_no_landmark)

    # Step 5: Extract City, State, and Street tokens
    city, state, street_tokens = extract_locality(tokens)

    # Step 6: Build canonical street representation
    street = build_street_string(street_tokens)

    # Step 7: Generate lexicographically sorted, deduplicated tokens
    all_normalized = set()
    if pincode:
        all_normalized.add(pincode)
    if premise_num:
        all_normalized.add(premise_num)
    if flat_no:
        all_normalized.add(flat_no)
        all_normalized.add("flat")
    if street:
        all_normalized.update(street.split())
    if landmark:
        all_normalized.update(landmark.split())
    if city:
        all_normalized.update(city.split())
    if state:
        all_normalized.update(state.split())
    all_normalized.add("india")

    # Filter out punctuation and empty strings
    sorted_tokens = sorted(t for t in all_normalized if t and t not in {",", ".", "-", "#", "/"})

    return AddressSlots(
        raw_input=raw_address,
        pincode=pincode,
        pincode_missing=pincode_missing,
        premise_number=premise_num,
        flat_no=flat_no,
        street=street,
        landmark=landmark,
        city=city,
        state=state,
        country="India",
        normalized_tokens=sorted_tokens,
    )
