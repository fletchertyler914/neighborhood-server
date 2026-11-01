# `/agent` / `/ai` playbook (for kids & parents)

Plain-English helper named **Crafter**. Type in chat (`/ai` for quick use, or `/agent`). Builds stay on your claim, stay undoable, and never need cheats or ops.

Rename anytime: set `display-name` in `data/plugins/NeighborhoodAgent/config.yml` (default `Crafter`), then restart Paper.

## How to talk to it

**In game:** `/ai help` or `/agent help` (also `what can you do`, `help builds`, `help shapes`…)

| Say… | What happens |
| --- | --- |
| `/builds` (aliases `/buildbook`, `/menu`) | Open the **Build Book** chest browser |
| `/builds book` or `/ai book` | Get Crafter’s Build Book item (right-click anytime) |
| `/ai menu` / `/ai builds` | Same Build Book GUI |
| `/ai …` or `/agent …` | Ask for something (build, give, spawn, day/night…) |
| `/ai undo that` | Undo the last Crafter change |
| `/agent good` | Mark the last job as good |
| `/agent bad <why>` | Mark it bad (helps the server get better) |

Examples: `/ai make it daytime` · `/ai give me oak planks` · `/agent spawn 3 pigs` · `/agent build me a chicken coop`

**Discover builds:** open `/builds` → pick a category (or Search) → click a build → Paste here. You can still say the name in chat (`/ai chicken coop`).

It may ask **one** simple question if something is unclear. It never needs JSON, tool names, or WorldEdit.

## Quick world stuff

- **Time:** day, noon, night, midnight — e.g. `/ai make it night`
- **Weather:** clear / sunny, rain, thunder — e.g. `/agent stop the rain`

## Stuff I can get / spawn

**Items (give)** — almost any normal Minecraft item, up to **64**.

- Try: `/ai give me 16 glass` · `/agent give me a diamond sword` · `/ai give me tnt`
- Looking at a block: `/ai give me these blocks` · `/agent give me that block` (stack of 64)
- **Not allowed:** command blocks, structure blocks, jigsaw, debug stick (admin/server tools only)

**Mobs (summon / spawn)** — any **spawnable living** Minecraft mob the server knows, up to **20**.

- Friendly: chicken, cow, pig, sheep, horse, wolf, cat, rabbit…
- Spicy: creeper, zombie, skeleton, blaze, enderman…
- Boss-ish: ender dragon (`dragon`), wither, warden, elder guardian…
- Try: `/ai spawn 3 chickens` · `/agent summon a dragon` · `/ai spawn 5 creepers`

## Shapes I can build

Sized shapes near you (not the fancy catalog builds). Say the **material + size**.

| Shape | Kind of ask | Example |
| --- | --- | --- |
| Wall | long × tall strip | `/agent build a cobblestone wall 20 long 5 high` |
| Platform / pad / deck | flat floor | `/ai 5x5 oak platform` |
| Enclosure (4 walls) | square / pen / yard / surround | `/agent 20x20 rock enclosure` · `/ai 15 by 20 stone enclosure 4 high` |
| Hollow box / room | shell, optional roof | `/agent glass box 8 by 8 by 5` |
| Solid box / cube | filled volume | `/ai solid stone box 5x5x5` |
| Cylinder / tower | round pillar | `/agent oak tower 10 tall` · `/ai quartz cylinder 3 wide 12 high` |
| Bridge | span water/gap (markers or look) | `/ai start marking a bridge` → place gold → `/ai finish the bridge` |
| Path / trail | cleared walkable trail | `/ai start marking a path` → place gold → `/ai finish the path` |
| Road | paved forward (or markers) | `/ai pave a road` · `/agent cobble road` |

**Best way (markers):** Place **gold blocks** as breadcrumbs in order, then finish.

1. Path: `/ai start marking a path` → walk & place gold blocks → `/ai finish the path` (optional: `5 wide`)
2. Bridge: `/ai start marking a bridge` → gold on each shore (optional mid) → `/ai finish the bridge`

Quick mode (no markers): look the way you want and say `/ai make a bridge` or
`/ai clear a path` — Crafter rays forward (water deck at surface). Fancy named
bridges (`rope bridge`) still use ready-made builds. Marker block is configurable
(`path-marker-block` in plugin config; default gold).

**Also:**

- **Finish this wall** — fill an open wall you’re looking at: `/agent finish this wall 12 blocks high with quartz`
- **Finish / clear floor** — second story, replace floor, clear floor: `/ai make a second floor` · `/agent clear this floor`
- **Undo** — `/ai undo that`

Rough size caps (it will say if too big): walls ~48×32, platforms ~32×32, enclosures/boxes ~32×32×24.

## Ready-made builds (gold catalog)

**Browse in game:** `/builds` (or right-click Crafter’s Build Book). Categories, search, then paste.

**101** curated pastes. You can also say the name like a kid would. If it isn’t on this list, Crafter may ask a clarifying question or offer a simple shape instead.

### Houses & shops
Apartment · Bakery · Beach hut · Blacksmith · Church · Desert house · Igloo · Inn · Library · Log cabin · Market stall · Medium cottage · Modern house · Mushroom house · Small cottage (`house`, `cottage`, `cabin`) · Stone cabin · Tavern · Townhouse · Treehouse

### Farms & animals
Bee house · Berry farm · **Carrot farm** (`carrots`, `carrot garden`) · Cow barn · Duck pond · **Garden plot** (`garden`, `flower garden`, `flowers please`) · Goat pen · Grain silo · Greenhouse · **Herb garden** · Horse stable · Kelp farm · Large / small chicken coop · Large / small pig pen · Melon / mushroom / potato / pumpkin / sugarcane / wheat farm · Rabbit hutch · Red barn · Sheep pen · Turkey pen · Windmill

### Forts & towers
Bell tower · Castle corner tower · Castle gate · Fortress · Gatehouse · Guard post · Lighthouse · Little castle · Observatory · Stone wall segment · Watchtower · Wizard tower

### Bridges & paths
Dock · Long pier · Moat bridge · Road · Rope bridge · Short oak bridge · Stone archway · Stone bridge · Train track · Wood wall (palisade) · Wooden suspension bridge

### Parks & decoration
Campground · Flag pole · Fountain · Gazebo · Graveyard · Koi pond · Lamp post · Hedge maze · Park bench · Picnic area · Playground · Shrine · Statue · Stone plaza · Tent camp · Village well · **Zen garden** (`calm garden`, `rock garden`)

### Nature
Dark oak tree · Large oak tree · Pond · Rock arch · Spruce / pine

### Utility
Armory · Enchanting room · Fishing hut · Furnace / smelter room · Large stable · Potion station · Storage shed · Warehouse · Water mill · Workshop

## Tips

1. **Be specific:** material + size → `cobblestone wall 20 long 5 high`, not just “a wall.”
2. **Square / 4 walls / pen / yard / surround** → enclosure (hollow walls), not a single wall.
3. **Named builds** (`chicken coop`, `flower garden`, `watchtower`) use the gold catalog; **sized shapes** (`tower 10 tall`, `5x5 platform`) use place_shape.
4. Stand where you want it. Builds go near **you**, on **your** claim.
5. Oops? `/ai undo that`. Still wrong? `/agent bad wrong_build` (or a short why).

Ops: weekly `make companion-gaps-export` reviews unfulfilled asks in SQLite
`request_gaps` → expand catalog/coverage from real demand.

## Builds & clearing ground

Builds go where you’re **looking**, or a few blocks in front of you. Saying
**build …** (or picking from `/builds`) clears a pad and pastes — no extra
`yes` step. Undo with `/ai undo that` if it was the wrong spot.

## Not yet

- Digging / quarrying / blowing big holes (`dig`, `mine out`, …) — refused; try a platform or wall instead
- Arbitrary WorldEdit, or building on someone else’s claim
- Admin-only blocks (command / structure / jigsaw / debug stick)
