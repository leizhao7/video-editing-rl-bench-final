# Piecewise Sync Rerun Medium Scores

Judge: OpenRouter `openai/gpt-5.5`; LLM judge is diagnostic.

Gemini 3.1 Pro is filled from the previous successful run because the current Google API Pro run hit quota/rate limits.

| model | note | run_exit | verify_exit | duration_sec | total | r_task | r_general | r_av_sync_segmented | r_av_sync_global | r_visual_artifact_cleanup | r_content_preservation | llm_overall | sync_median_residual_ms | hard_cap_value |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| claude-sonnet-4.6 |  | 0.000 | 0.000 | 89.767 | 0.677 | 0.641 | 0.822 | 0.255 | 0.235 | 1.000 | 0.940 | 0.544 | 550 | 1.000 |
| gemini-3.1-pro-preview | carried from previous successful run; current Google API Pro run was quota/rate-limited | carried | carried | 88.234 | 0.633 | 0.612 | 0.717 | 0.292 | 0.358 | 0.650 | 0.804 | 0.558 | 300 | 0.650 |
| gpt-5.4-mini |  | 0.000 | 0.000 | 92.600 | 0.605 | 0.548 | 0.832 | 0.264 | 0.162 | 0.547 | 0.952 | 0.490 | 600 | 1.000 |
| claude-opus-4.7 |  | 0.000 | 0.000 | 94.000 | 0.589 | 0.507 | 0.919 | 0.181 | 0.175 | 0.497 | 0.962 | 0.504 | 650 | 0.700 |
| gpt-5.5 |  | 0.000 | 0.000 | 90.682 | 0.576 | 0.499 | 0.882 | 0.269 | 0.125 | 0.498 | 0.930 | 0.453 | 700 | 0.700 |
| gpt-5.4 |  | 0.000 | 0.000 | 95.467 | 0.525 | 0.446 | 0.837 | 0.195 | 0.189 | 0.161 | 0.955 | 0.466 | 650 | 0.700 |
| claude-haiku-4.5 |  | 0.000 | 0.000 | 91.904 | 0.512 | 0.432 | 0.832 | 0.175 | 0.202 | 0.195 | 0.892 | 0.459 | 600 | 0.650 |
| gemini-3.1-flash-lite |  | 0.000 | 0.000 | 96.782 | 0.471 | 0.399 | 0.762 | 0.196 | 0.189 | 0.165 | 0.902 | 0.392 | 650 | 0.700 |

Full TSV: `reports/piecewise_sync_rerun_medium_scores.tsv`
