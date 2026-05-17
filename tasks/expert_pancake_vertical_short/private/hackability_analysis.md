# Hackability Analysis

## Main hacking risks

- Submit any vertical video, generated footage, or unrelated source material.
- Use novice/blooper/reaction/end-card segments instead of the expert tutorial region.
- Delete most of the source to avoid negative material while losing recipe steps.
- Reorder clips into a plausible but non-causal montage.
- Fake vertical format with black bars, blurred padding, or a decorative landscape container.
- Add captions that are invisible, oversized, misplaced, generic, or unrelated to the visible action.
- Claim source ranges and captions in JSON without rendering the corresponding edit.

## Anti-hacking defenses

- Source authenticity and frame matching penalize external, generated, or unmatched material.
- Private allowed and negative source intervals score tutorial purity and penalize novice/blooper/end-card leakage.
- Private visual step intervals require pan prep, batter, bubble cue, flip, and plating coverage.
- Source-time monotonicity and step order checks penalize non-causal rearrangements.
- Vertical reframe checks detect fake portrait padding and weak crops.
- Caption visibility, step-caption completeness, caption/action alignment, and LLM caption rubrics bound caption hacks.
- Hard caps apply for missing output, wrong aspect, fake vertical format, heavy negative material, external material, weak step coverage, severe order failure, missing captions, and weak semantic captions.

## Hackability classification

Source-region selection, visual step coverage, temporal order, and source authenticity are hard-to-hack because they depend on private intervals and source-frame matching. Caption and crop quality are hackable but bounded because readability, placement, fake padding, ROI containment, and visual/source consistency checks catch the main hacks. The LLM judge is soft/vibes and used as a minority semantic layer.
