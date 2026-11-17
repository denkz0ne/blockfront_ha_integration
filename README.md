# BlockFront Stats for Home Assistant

Home Assistant integration for a configured BlockFront player. It reads public player, match, and brigade pages from [Vuis BFStats](https://vuis.dev/bfstats/). An optional [official BlockFront API](https://docs.blockfrontmc.com/api/) key fills supported values when the public Vuis page does not provide them.

## Setup and upgrade

Install through HACS and restart Home Assistant manually. On setup, enter the player's Minecraft name. The UUID field is optional: the integration reads the public Vuis player profile and stores the UUID internally to keep entity identities stable. If an official API key is supplied, it is validated against that player and is sent only to the configured official API URL.

Existing entries migrate to Vuis as the primary source. Valid official API keys from v0.9.0 are retained as optional fallbacks. Previous-provider credentials are not reused. Existing recorder history is not rewritten, and unsupported old entities are integration-disabled rather than deleted.

## Data and refresh

The integration creates selected sensors for:

- Player profile, career statistics, rank progress, and the eight classes shown on Vuis.
- The latest match result, personal score and combat line, placement, map, mode, team, exact end time, and the two team totals.
- Brigade name, tag, your role, member count/capacity, rank, and score.
- Bootcamp completion as a binary sensor.

Vuis map pages, map statistics, the full latest-match player table, match duration, team casualties, global online count, official monthly standings, map ratings, captures, K/HS, and Commander XP are not exposed as integration entities.

In **Configure**, entity selection controls both created sensors and endpoint polling. Profile and latest-match pages default to 15 minutes; brigade pages default to 30 minutes. Vuis requests are serialized and separated. The refresh button requests an update for every enabled endpoint.

Time played is converted from Vuis hours to seconds for Home Assistant. Vuis rounds that source value to a tenth of an hour; the sensor attributes mark the converted value as rounded. Rank progress is also provided as current XP, required XP, remaining XP, and percentage. Career win rate is calculated from wins and games. Ratios are numeric and rounded to two decimals.

An official API key is optional. When configured, exact matching fields fill null Vuis fields; it does not replace a value already returned by Vuis. If a Vuis profile or match page is temporarily unavailable, the official API may supply the corresponding private dataset. The key is never sent to Vuis. Official routes still require an authorized key.

## Dashboard

`examples/blockfront-dashboard.yaml` is the dashboard example for the selected Vuis and official API entities. It keeps a compact light design and the existing profile, match, combat, and class views while excluding the removed maps and global data. The live dashboard is not changed automatically by installing the integration.

## Source limitations

Vuis currently exposes these values as rendered HTML rather than a documented JSON API. The integration reads the public profile, matches, brigade, brigade scoreboard, and latest-match pages. If Vuis changes its page structure, affected entities may become unavailable until the parser is updated. No credentials are used for Vuis.

The official API profile schema documents `stats: {}` without enumerating all fields. Only known matching scalar fields are used as fallbacks; undocumented units and equivalent meanings are not inferred.

## Development

See [source and migration notes](docs/official-api-migration.md). The repository includes transport and config-flow coverage under `tests/`.
