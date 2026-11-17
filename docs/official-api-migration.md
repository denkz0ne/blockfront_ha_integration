# Vuis and official API data flow

Vuis BFStats pages are the primary public source. The official BlockFront API is an optional authenticated supplement and fallback.

## Public Vuis routes

| Vuis page | Data | Integration entities |
|---|---|---|
| `/bfstats/players/{username}/stats` | UUID, rank and XP progression, career statistics, class XP, brigade tag | `vuis_profile` sensors and bootcamp binary sensor |
| `/bfstats/players/{username}/matches` | Newest match, result, personal score line, placement, map, mode, team, relative end time, match detail link | `vuis_matches` summary sensors |
| `/bfstats/match/{match_id}` | Exact UTC end time and Allies/Axis scores, when the page identifies team order | `latest_match_end`, `latest_match_allies_score`, `latest_match_axis_score`; player rows are discarded |
| `/bfstats/brigades/{tag}` | Brigade name/tag, member count/capacity, configured player's role | `vuis_brigade` sensors |
| `/bfstats/scoreboards/brigades` | Configured brigade's current rank and score only | `brigade_rank`, `brigade_score` |

The parser does not create entities for UUID, K/HS, captures, Commander XP, map pages, the full match roster, match duration, team casualties, global player count, monthly standings, or map ratings. UUID remains the config-entry unique ID and is not exposed as a sensor.

Vuis returns HTML. Each page family has its own coordinator and refresh interval. Requests share a serialized Vuis client. A latest-match detail failure leaves the match's other fields usable; brigade summary and scoreboard can also refresh independently when only one page fails.

## Optional official API fallback

An API key is stored in the config entry and sent only in `X-API-Key` headers to the configured official API base URL. The key is never added to Vuis requests, URLs, logs, or diagnostic attributes. Official `player`, `player_matches`, `clan`, and `match` responses fill only null or unavailable fields. Existing Vuis values take precedence. If Vuis profile or match parsing fails, the corresponding authorized official endpoint can provide a fallback dataset. Public official endpoints for online count, monthly scoreboard, maps, and ratings are not polled.

The profile and matches coordinators keep failures independent. A failed official fallback does not make usable Vuis data unavailable. Empty/missing fields remain unknown rather than becoming zero. No assumptions are made about undocumented stat names or units.

## Identity and migration

Setup validates the Minecraft username and reads the public Vuis profile. UUID input is optional; when omitted, the profile avatar URL supplies the UUID before the config entry is created. A supplied UUID must match the public profile. The UUID is persisted as the config entry's unique ID, preserving existing UUID-based entity identities.

Version 5 retains the valid official API key from v0.9.0, resets old endpoint/entity selections to the newly selected Vuis datasets, and leaves historical recorder data untouched. Earlier-provider credentials are discarded. Entities outside the new catalog, including excluded map/global/match-detail entities, are integration-disabled rather than removed. User-disabled entities remain disabled.

## Values and semantics

- Vuis play time is shown in rounded tenths of an hour. The existing `time_played` sensor remains seconds (`hours × 3600`) for Home Assistant compatibility; attributes state that it is rounded.
- K/D is numeric and rounded to two decimal places. Rank progress is available as XP progress, XP required, XP remaining, and percent.
- Match team scores are assigned to Allies/Axis from the page's team order; the official match endpoint supplies named values if the Vuis order is unavailable.
- Match date is parsed from the detail page's explicit UTC timestamp. The relative time remains a diagnostic attribute.
- No profile history is fabricated. Home Assistant recorder history can chart the new sensor values going forward.

The official API v2 profile example documents `stats: {}` without a full field schema. Only exact known fields are mapped as fallbacks. Official routes that require a key are not requested unless one is configured.
