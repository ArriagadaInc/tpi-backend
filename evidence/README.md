# Evidencia del Harness

Hechos verificables por tarea. Nunca secretos, credenciales, URLs prefirmadas ni PII.

```text
evidence/<task_id>/
  developer/   developer-NN.json                (evidence.py)
  reviewer/    review-NN.json, candidate_review-NN.json
  deployment/  merge, candidate, deployment, verification, rollback, failure
  approvals/   approval, acceptance, resolution  (solo approve.py, humano, terminal interactiva)
  transitions.jsonl                              (transition.py)
  aws-audit.jsonl                                (aws_guard.py, redactado)
```

Schema: `harness/schemas/evidence.schema.json`. Los agentes no editan esta carpeta con herramientas
de edicion: escriben via `python scripts/harness/evidence.py write --kind <kind> --input <archivo>`.
