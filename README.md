# BlockFront Stats — Official API

Home Assistant integration using only the [official BlockFront API](https://docs.blockfrontmc.com/api/).

## Installation and upgrade

Add `https://github.com/denkz0ne/blockfront_ha_integration` to HACS as an Integration. Install/update and restart Home Assistant manually. Existing entries migrate automatically to the official URL and retain their player UUID. Previous provider URLs, keys and polling settings are removed; a key from another provider is never sent to the official API. Recorder history is not modified.

New setup asks for a display name, Minecraft UUID, official API base URL and optional **official** API key. Public data works without a key. The UUID can be copied from your previous integration entry.

## Public and authorized modes

Without a key: online player count, your monthly score/position/reset and optional selected-map statistics and ratings.

With a valid official key: player profile, per-class XP and recent matches, plus optional brigade metadata and latest-match team scores/casualties. Keys are sent only in `X-API-Key` on authorized routes. Private requests are never attempted without a key. An entered key is checked against your player profile before saving. Blank key input keeps the saved key; **Remove saved API key** clears it.

Under Configure, **Enabled data and entities** selects each individual metric. Unselected entities are integration-disabled, not deleted. Endpoints with no selected metrics stop polling (dependencies may still be required by another selected endpoint). On first adding a key, supported profile and recent-match metrics are enabled automatically. User-disabled registry entities stay disabled.

Private metrics are not created without a key; existing private entries are integration-disabled. Returning to authorized mode reuses their original UUID-based unique IDs. Unsupported old analytics/history/inventory/progression entities are no longer provided and remain disabled in the registry; existing recorder history is retained. No migration changes entity IDs or rewrites historical values.

## Semantics and limitations

Online count keeps its original identity and `players` unit. Equivalent personal metrics retain their previous identity, units and state classes. Monthly score is a new entity and never substitutes for XP, skill rank, career totals or season history. Global map/team metrics are never used as personal statistics. Time values documented in milliseconds are converted to UTC timestamps; map win rates are converted to percent. Empty or unavailable data does not become zero.

The official profile example documents `stats: {}` without listing field names or units. The adapter supports exact existing stat keys, rank title, documented `class_exp`, and documented match fields; undocumented keys are not guessed. After an authorized response, extra scalar profile fields appear in Configure for explicit selection under their API field names. They receive new identities with no assumed units; existing career IDs are never reused for unverified fields. Full personal coverage, including play-time units and skill-rank shape, requires live verification with an authorized key. No key is currently available for end-to-end testing.

Map metrics use the selected map/mode/team, avoiding hundreds of automatically generated entities. Map ratings use the selected map/mode, with votes including zero-star votes when supplied. Brigade and match details default off. Privacy-hidden standings are not exposed.

| Dataset | Default interval |
|---|---:|
| Online count | 60 seconds |
| Monthly standing | 300 seconds |
| Map statistics | 900 seconds |
| Map ratings | 3600 seconds |
| Profile / recent matches | 900 seconds |
| Brigade metadata | 1800 seconds |
| Latest match details | 900 seconds |

The shared client spaces requests, honors Retry-After on 429/503 and reuses ETag responses after 304. Official limits are 4 requests/second/IP without a key; authorized limits are 20/second/IP and 10/second/key. A shared-IP client can consume allowance independently. The integration does not fabricate a remaining-request counter. Dataset failures do not take down unrelated endpoints.

The dashboard example retains the previous light design but includes historical personal/history cards; those require matching data and some historical service-specific cards are obsolete after this reconstruction. It is not an automatic dashboard migration.

## Development

See [migration design](docs/official-api-migration.md). Tests cover transport failures, conditional caching, backoff, public/private key isolation, normalized values, migration and entity selection. GitHub Actions runs tests, Ruff, HACS validation and hassfest.
