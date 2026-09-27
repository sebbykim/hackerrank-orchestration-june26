# Evaluation Report

## Run mode

ANTHROPIC_API_KEY was not present; evaluation used deterministic mock fallback clients under the two required Claude configuration labels.

Each configuration ran with an isolated temporary local cache so model IDs could not share cached responses during comparison.

## Headline metrics

| config | claim_status_macro_f1 | risk_flags_jaccard | supporting_image_ids_jaccard | runtime_s | model_calls | paid_model_calls |
|---|---:|---:|---:|---:|---:|---:|
| claude-sonnet-4-6 (mock fallback; ANTHROPIC_API_KEY missing) | 0.250 | 0.347 | 0.750 | 1.041 | 20 | 0 |
| claude-opus-4-8 (mock fallback; ANTHROPIC_API_KEY missing) | 0.250 | 0.347 | 0.750 | 1.009 | 20 | 0 |

## Claim status confusion matrices

### claude-sonnet-4-6 (mock fallback; ANTHROPIC_API_KEY missing)
| expected \ predicted | supported | contradicted | not_enough_information |
|---|---:|---:|---:|
| supported | 12 | 0 | 0 |
| contradicted | 5 | 0 | 0 |
| not_enough_information | 3 | 0 | 0 |

### claude-opus-4-8 (mock fallback; ANTHROPIC_API_KEY missing)
| expected \ predicted | supported | contradicted | not_enough_information |
|---|---:|---:|---:|
| supported | 12 | 0 | 0 |
| contradicted | 5 | 0 | 0 |
| not_enough_information | 3 | 0 | 0 |

## Per-field accuracy

### claude-sonnet-4-6 (mock fallback; ANTHROPIC_API_KEY missing)
| field | exact_accuracy |
|---|---:|
| evidence_standard_met | 0.850 |
| evidence_standard_met_reason | 0.000 |
| issue_type | 0.400 |
| object_part | 0.850 |
| claim_status | 0.600 |
| claim_status_justification | 0.000 |
| valid_image | 0.900 |
| severity | 0.350 |

### claude-opus-4-8 (mock fallback; ANTHROPIC_API_KEY missing)
| field | exact_accuracy |
|---|---:|
| evidence_standard_met | 0.850 |
| evidence_standard_met_reason | 0.000 |
| issue_type | 0.400 |
| object_part | 0.850 |
| claim_status | 0.600 |
| claim_status_justification | 0.000 |
| valid_image | 0.900 |
| severity | 0.350 |

## Operational analysis

- Sample evaluation rows: 20 labeled claims, 29 images.
- Full test set scale: 44 input claims, 82 images.
- Token assumptions per claim: 900 text input, 1200 input per image, 450 output.
- Vision is treated as input tokens. Costs below use rough token assumptions, not SDK usage telemetry.
- Sample token estimate: 52800 input, 9000 output.
- Full test token estimate: 138000 input, 19800 output.
- Full test Sonnet estimate: $0.7110.
- Full test Opus estimate: $1.1850.
- Batch API cost multiplier assumption: 0.5; prompt cache write/read multipliers: 1.25/0.1.
- Batching should group independent claim rows while preserving one VLM call per claim; cache hits should be checked before scheduling paid calls.
- Each configuration ran with an isolated temporary local cache so model IDs could not share cached responses during comparison.
- The Claude client uses bounded retry with backoff, then the pipeline emits a valid fallback row if retries are exhausted.
- claude-sonnet-4-6 (mock fallback; ANTHROPIC_API_KEY missing) runtime: 1.041s; approx throughput 1152.2 requests/minute, 3560330.0 tokens/minute.
- claude-opus-4-8 (mock fallback; ANTHROPIC_API_KEY missing) runtime: 1.009s; approx throughput 1189.6 requests/minute, 3675725.0 tokens/minute.
