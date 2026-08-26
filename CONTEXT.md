# CONTEXT.md — Domain Knowledge, Business Logic & External Contracts

> **Critical:** Read this before touching any business logic. Violations here cause incorrect premise matching in production — billing errors, undeliverable field agent routes, and SAP data corruption.

---

## 1. Domain: GIS-Based Address Base Premium System

### What This System Does
This system is the **search and disambiguation gateway** for a GIS Address Base Premium platform integrated with SAP S/4HANA. Its output (`sap_premise_id`) is used by:
1. **SAP Billing Engine** — to look up utility billing records for a property
2. **Field Agent Routing** — to generate GPS coordinates for meter-reading, maintenance visits
3. **Premise Onboarding** — to validate a new address before it is registered in SAP
4. **Customer Portal Search** — to allow end-users to find and confirm their address (Blinkit/Zomato-style UX)

### Why Accuracy is Non-Negotiable
A wrong `sap_premise_id` returned with high confidence results in:
- Utility bills sent to the wrong premise → legal liability
- Field agents dispatched to wrong location → operational cost + SLA breach
- Duplicate premise records in SAP → data integrity failure

**Threshold policy:**
- If `confidence_score < 0.75`: return candidates but set `resolved = null`. Force user confirmation.
- If `confidence_score >= 0.75 and < 0.88`: return best match but flag for review audit log.
- If `confidence_score >= 0.88`: auto-resolve (no human review required).

---

## 2. Indian Address Structure — Domain Knowledge

### Official Address Hierarchy (India Post Standard)
```
Level 1: Country         → India
Level 2: State           → Bihar
Level 3: District        → Patna District
Level 4: City/Town       → Patna
Level 5: Locality/Area   → Boring Road Area
Level 6: Street          → Mahatma Gandhi Road
Level 7: Premise No.     → 42
Level 8: Sub-Premise     → Flat 7B
Level 9: Pincode         → 800001
```

### The Pincode as Spatial Anchor (CRITICAL RULE)
**The 6-digit India Post PIN code is the single most important disambiguator.**
- It is hierarchical: first digit = postal zone, digits 1-2 = state, digits 1-3 = sorting district, all 6 = delivery post office.
- PIN `800001` uniquely identifies Patna Head Post Office area (Patna, Bihar).
- PIN is present in ~89% of digitally submitted Indian addresses.
- When absent, fall back to city → state → landmark for spatial bounding.
- **Never assume a pincode is wrong.** If pincode and city conflict (e.g., `800001` + `Mumbai`), flag `pincode_city_mismatch=True` and trust the pincode.

### Common Indian Address Abbreviation Patterns

| Full Form | Abbreviations (all must be handled) |
|-----------|-------------------------------------|
| Road | Rd, Rd., Rdw, Marg, Mrg |
| Street | St, St., Str |
| Mahatma Gandhi | MG, M.G., M.G, Gandhi, Mahatma Gandhi |
| Jawaharlal Nehru | JL, J.L., Nehru, J.L.N. |
| Flat | Fl, Fl., #, Apt, Apt. |
| Near | Nr, Nr., Nrby |
| Opposite | Opp, Opp. |
| Bihar | BR, B.R. |
| Maharashtra | MH, M.H. |
| Delhi | DL, D.L., NCR |
| Karnataka | KA, K.A. |
| India | IN, IND, Bharat |

### Sub-Premise Formats (must all resolve to `flat_no`)
| Input | Normalized `flat_no` |
|-------|---------------------|
| `Flat 7B` | `7b` |
| `Fl. 7B` | `7b` |
| `#7B` | `7b` |
| `#7-B` | `7b` |
| `7/B` | `7b` |
| `Suite 7B` | `7b` |
| `Apt 7B` | `7b` |
| `Unit 7-B` | `7b` |

---

## 3. SAP Integration Contracts

### SAP Premise ID Format
```
Format: PR-{PINCODE}-{PREMISE_NO}-{FLAT_NO}
Example: PR-800001-42-7B

Rules:
- PINCODE: always 6 digits
- PREMISE_NO: alphanumeric, max 10 chars, uppercase
- FLAT_NO: alphanumeric, max 10 chars, uppercase  
- If no flat (independent house): PR-{PINCODE}-{PREMISE_NO}
```

### SAP Source Databases
| Source | Type | Contains | Read Method |
|--------|------|---------|-------------|
| `SAP_HANA` | SAP S/4HANA | Master premise records, billing accounts | HANA JDBC / SAP RFC |
| `GIS_POSTGIS` | PostgreSQL + PostGIS | Spatial polygons, lat/long, geohash, satellite-verified addresses | Async psycopg2 |
| `BILLING_ORACLE` | Oracle 19c | Historical billing addresses (legacy) | cx_Oracle async |

### Data Freshness SLA
| Source | CDC Lag Target | Acceptable Max |
|--------|---------------|---------------|
| SAP_HANA | <500ms | 2 minutes |
| GIS_POSTGIS | <500ms | 2 minutes |
| BILLING_ORACLE | <2 hours | 6 hours |

---

## 4. Confidence Score Business Rules

```python
# These thresholds are in config.py and configurable via env vars
# DO NOT hardcode these values in engine code

TIER1_CONFIDENCE_THRESHOLD = 0.92   # Auto-resolve from Tier 1
TIER2_CONFIDENCE_THRESHOLD = 0.88   # Auto-resolve from Tier 1+2 fused score
MANUAL_REVIEW_THRESHOLD    = 0.75   # Return candidates, require user confirmation
DISCARD_THRESHOLD          = 0.50   # Return "no match found"
```

**Confidence Degradation Rules:**
1. If `pincode_missing=True`: cap max confidence at `0.80` regardless of score
2. If `flat_no_missing=True`: cap max confidence at `0.85` (cannot distinguish flats in a building)
3. If `circuit_breaker.state == OPEN`: all T3 results get `confidence_degraded=True`

---

## 5. User Roles & Access Control

| Role | Access | API Key Scope |
|------|--------|--------------|
| `READ_ONLY` | `GET` endpoints only, `/v1/search/*` | `scope:search` |
| `SEARCH_API` | `/v1/search/*` (POST included) | `scope:search` |
| `ADMIN` | All endpoints including `/v1/admin/*` | `scope:search scope:admin` |
| `INTERNAL_WORKER` | Ingestion worker — can call `/v1/admin/reindex` | `scope:admin` |

---

## 6. External Service Contracts

### Google GenAI (Embedding + LLM)
- **Embedding model:** `text-embedding-004` (768 dimensions)
- **LLM model:** `gemini-2.5-flash-001` (T3 disambiguator)
- **Rate limits:** 60 RPM (free tier), 1500 RPM (paid)
- **Timeout:** 3 seconds (circuit breaker triggers if exceeded)
- **Batching:** Max 64 texts per `embed_content()` call

### Circuit Breaker Parameters (Tier 3 LLM)
```python
CIRCUIT_BREAKER_THRESHOLD  = 5      # consecutive failures → OPEN
CIRCUIT_BREAKER_TIMEOUT    = 60     # seconds in OPEN state → HALF-OPEN test
```

---

## 7. Key Algorithmic Invariants (Do Not Break)

1. **Spatial Partitioning Always First:** Every search MUST pre-filter by pincode before any similarity computation. Without this, we compute fuzzy scores against 500M records instead of <15K.

2. **Token Set Ratio is Order-Invariant by Design:** `"Flat 7B, 42 MG Rd"` and `"42 MG Rd, Flat 7B"` must score 1.0. Do not replace this with Levenshtein or simple string matching.

3. **Number Blindness Guardrail:** Dense embedding models cannot reliably distinguish `7A` from `7B`. Always extract `premise_number` and `flat_no` as hard SQL filters before cosine similarity. This is non-negotiable.

4. **Graceful Degradation over Hard Failure:** If Gemini is unavailable (T3 circuit open), return the best T1/T2 result with `confidence_degraded=True` and log a warning. Never raise a 500 to the caller.

5. **Bidirectional Abbreviation Dictionary:** The dictionary must support: `"M.G. Rd"` → `"mahatma gandhi road"` AND `"mahatma gandhi road"` → canonical form. Normalization must always produce the same canonical token list regardless of which abbreviation was used as input.
