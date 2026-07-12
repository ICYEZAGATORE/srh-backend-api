# Step 5 — Convergence (winning configs, logging added only)

## safety (XGBoost, winning config)
- logloss: train 0.656→0.162; validation min 0.425 at round 145/400, ending 0.454.
- **Converged** — train loss decreases monotonically, validation loss flattens after ~round 145; mild overfitting after the minimum (train↔val gap 0.292).
- Plot: `results/convergence_safety.png`

## topic (XGBoost, winning config)
- mlogloss: train 1.767→0.020; validation min 0.107 at round 299/300, ending 0.107.
- **Converged** — train loss decreases monotonically, validation loss flattens after ~round 299; no material overfitting (train↔val gap 0.087).
- Plot: `results/convergence_topic.png`

## language (Logistic Regression, winning config)
- lbfgs reports internal convergence at n_iter≈15; train/val log-loss both fall then plateau by ~40 iterations (final train 0.0355, val 0.0363).
- **Converged, no overfitting** — the small, stable train↔val gap matches the perfectly-separable char-n-gram feature space (val F1 = 1.0).
- Plot: `results/convergence_language.png`
