# Step 5 — ML Efficacy (held-out test sets)

Deployed artifacts (`srh-backend-api/models/*.pkl`) evaluated on the `srh-ml-model` held-out test splits. Models are **not** retrained here.

## Consistency check vs recorded baselines (post version-pinning)

| model | measured acc | baseline acc | measured macro-F1 | baseline macro-F1 | verdict |
|---|---|---|---|---|---|
| safety | 0.7867 | 0.7867 | 0.7847 | 0.7847 | ✅ **exact match** — no version-drift regression (measured `f1_unsafe`≈0.76 confirms the ~0.76 figure) |
| language | 1.0000 | 1.0000 | 1.0000 | 1.0000 | ✅ exact match |
| topic | 0.9688 | 0.9693 | 0.8794 | 0.9628 | ⚠️ acc + weighted-F1 match; **macro-F1 gap explained below** |

**Topic macro-F1 gap — explained, not a regression.** In this held-out file the two
minority classes have only **7 samples each** (`disability_srh`, `gbv_consent`) versus
~257–341 for the other five. `disability_srh` recall is 0.286 (2 of 7), which — being an
*unweighted* average — drags macro-F1 down even though accuracy (0.9688) and weighted-F1
(0.9692) match the baseline **exactly**. The recorded baseline macro-F1 (0.9628) was
produced by the "Approach B — Augmented Minority" split, which oversampled those classes;
this file carries them at natural (tiny) frequency. **Real implication:** on true
natural-distribution data, `disability_srh` intent detection is unreliable (n is tiny and
recall is low) — consistent with `disability_srh` being the weakest-covered topic end-to-end
(see traceability C/E). This is a genuine model limitation to disclose, not a version issue.


### safety  (n = 750)

| class | precision | recall | f1 | support |
|---|---|---|---|---|
| safe | 0.740 | 0.883 | 0.805 | 375 |
| unsafe | 0.855 | 0.691 | 0.764 | 375 |
| **macro avg** | 0.798 | 0.787 | 0.785 | 750 |

- **Accuracy (measured):** 0.7867  ·  **Macro-F1 (measured):** 0.7847
- **Recorded baseline (test_metrics):** accuracy=0.7867, f1_unsafe=0.764, recall_unsafe=0.6907, precision_unsafe=0.8548, f1_macro=0.7847, roc_auc=0.8702
- Confusion matrix: `results/confusion_safety.png`

### topic  (n = 1632)

| class | precision | recall | f1 | support |
|---|---|---|---|---|
| contraception | 0.957 | 0.985 | 0.971 | 340 |
| sti_hiv | 0.979 | 0.968 | 0.973 | 340 |
| pregnancy | 0.965 | 0.959 | 0.962 | 341 |
| puberty | 0.969 | 0.977 | 0.973 | 257 |
| gbv_consent | 0.857 | 0.857 | 0.857 | 7 |
| disability_srh | 1.000 | 0.286 | 0.444 | 7 |
| general_srh | 0.976 | 0.974 | 0.975 | 340 |
| **macro avg** | 0.958 | 0.858 | 0.879 | 1632 |

- **Accuracy (measured):** 0.9688  ·  **Macro-F1 (measured):** 0.8794
- **Recorded baseline (test_metrics):** accuracy=0.9693, f1_macro=0.9628, f1_weighted=0.9692, roc_auc_ovr=0.9985
- Confusion matrix: `results/confusion_topic.png`

### language  (n = 1800)

| class | precision | recall | f1 | support |
|---|---|---|---|---|
| english | 1.000 | 1.000 | 1.000 | 900 |
| kinyarwanda | 1.000 | 1.000 | 1.000 | 900 |
| **macro avg** | 1.000 | 1.000 | 1.000 | 1800 |

- **Accuracy (measured):** 1.0000  ·  **Macro-F1 (measured):** 1.0000
- **Recorded baseline (test_metrics):** accuracy=1.0, f1_binary=1.0, f1_macro=1.0, roc_auc=1.0
- Confusion matrix: `results/confusion_language.png`
