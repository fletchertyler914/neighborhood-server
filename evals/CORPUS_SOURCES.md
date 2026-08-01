# Grounded corpus sources

Intent taxonomy for `evals/eighty_seed.yaml` is triangulated from:

| source_id | Signal | Use |
| --- | --- | --- |
| `builds.house_base` | Community build showcases skew house/base (e.g. r/Minecraftbuilds flair mix) | Named gold: cottage/house/cabin |
| `builds.farm_animals` | Creative farm aesthetics / animal pens common in tutorials & catalogs | Coop, barn, pens, stable |
| `builds.landmark` | Castles, bridges, towers, lighthouses frequent showcase themes | Gold castle/bridge/watchtower |
| `builds.sitework` | Walls, platforms, simple rooms as construction primitives | `place_shape` |
| `play.creative_mode` | Creative is a major mode share especially Bedrock/crossplay | Skew corpus to build/helpers |
| `research.basalt` | MineRL BASALT village house / animal pen style tasks | Map to paste/finish, not motor RL |
| `product.neighborhood` | Friends creative + Floodgate kids on this server | Day/night, give, undo, short prompts |

Limits: MineRL survival diamond demos are **not** used as NLS labels. GrabCraft/BuildPaste category sizes inform intent inventory only — not auto-mapped schematics.

## Wave 2 seed shape

`evals/eighty_seed.yaml` is the grounded synthetic corpus for ~80% ordinary kid/adult `/agent` asks. It has 146 deterministic rows, including 22 held-out paraphrases. Rows carry:

- `source_ids[]` — citations into the table above
- `paraphrase_family` — cluster for bucket reporting
- `intent_id` — tool-level intent (optional)
- `holdout: true` — reserved paraphrases (~12%) for overfitting checks
- `prior` — last-action context for session revise cases
- `perception.finishable_opening` — a synthetic semantic fixture proving a
  sized wall becomes `finish_wall`, not a free-standing `place_shape`, when
  the trusted gateway reports an opening

### Intent → tool map (product truth)

| Taxonomy weight | Examples | Expect |
| --- | --- | --- |
| Shelter / house | cottage, cabin, treehouse | gold `paste_template` or clarify if vague |
| Farm & animals | coop, pen, stable, bee house | gold `paste_template` |
| Landmarks | castle, bridge, watchtower, lighthouse, windmill | gold `paste_template` |
| Site work | wall/platform/box/tower-N-tall/cylinder | `place_shape` |
| Ambiguous wall NxN | `wall 20x20` | clarify long vs square |
| Contextual finish | finish wall/floor, second floor | `finish_wall` / `finish_floor` |
| Visible opening + sized wall | “build a wall 20 long 8 high” at an opening | `finish_wall`, with native geometry re-check |
| World comfort | day/night, sun/rain | `set_time` / `set_weather` |
| Inventory & friends | give diamonds, spawn chickens | `give_item` / `summon_entity` |
| Fix / undo | undo, never mind | `undo_last` / cancel |
| Safety negatives | hostiles, dig holes, over-budget | refuse |
| Non-gold named builds | igloo, wizard tower, observatory | clarify (not junk paste) |
| Revise follow-ups | taller / bigger / use oak | session revise on last build |
| Hard 20% | multi-modifier stacks, terrain sculpt | unresolved or clarify |

### How to run

```bash
make companion-corpus   # ALL eighty_seed rows + per-bucket report (no model)
make companion-gate     # locked SLO mix; never truncates product corpus rows
```

Live world probes stay small (`make companion-live` shapes suite) — offline corpus proves routing; live proves postconditions.

### Validation checklist

1. Coverage: each high-weight taxonomy node has ≥1 intent and ≥3 paraphrases.
2. Citation: every cluster has ≥1 `source_id` above.
3. Tool fidelity: `make companion-corpus` near-100% on seed + holdout.
4. Live spot-check (optional): small firecrab93 sample for place/finish/paste — not the whole corpus.

## Weekly feedback → corpus loop

Keep the product corpus honest with a short weekly triage (15–30 min):

```bash
make companion-feedback-export   # or: make companion-triage
# Inspect data/companion-feedback-export.jsonl
# Bucket bad rows: wrong_build / wrong_place / wrong_size / other
# For each cluster: add eighty_seed case(s) OR gold/alias fix
make companion-corpus
make companion-gate
```

| Bucket | Typical fix |
| --- | --- |
| `wrong_build` | Wrong template / finish vs place — gold alias or `finishable_opening` seed |
| `wrong_place` | Free-standing shape when opening visible — opening rewrite / live finish case |
| `wrong_size` | NxN wall clarify or budget refuse — grammar seed |
| `other` | Tag better next time (`/agent bad wrong_build …`) |

Players rate with `/agent good` or `/agent bad wrong_build|wrong_place|wrong_size <note>`.
`make companion-triage` prints the bucket summary and the next-step checklist.
If the feedback DB is empty, start from the seed rows already in
`evals/eighty_seed.yaml` under `finish.wall.opening.*` and `paste.nongold.*`.
