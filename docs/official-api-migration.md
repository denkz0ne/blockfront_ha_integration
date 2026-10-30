# Official API reconstruction

Only the official configurable API v2 URL is used. Public groups: player_count, scoreboard, map_stats, map_ratings. Optional key groups: player, player_matches, clan and latest match. X-API-Key is never sent on public requests, logged, or included in diagnostics. Redirects are disabled.

Preserve UUID-based unique IDs, original units and state classes only for equivalent profile/match/online values. Unsupported legacy entities remain in the registry and recorder without being provided. No recorder edits or entity deletions. Key-dependent registry entries are integration-disabled without a key and re-enabled only if disabled by this integration. User-disabled entities remain disabled.

One coordinator per endpoint; individual data selection controls entity registration and endpoint polling. Private requests require a configured key. Public failures remain independent. Cache by request parameters and authorization context; 304 needs a valid cache. Shared throttling and Retry-After apply across groups. Empty arrays are valid, missing numbers never become zero. A failed update makes its sensors unavailable.

Monthly score/rank are new metrics, never career/skill replacements. Millisecond timestamps become UTC timestamps. Map winRate is converted from ratio to percent; map/team data is never assigned to personal entities. No mass creation per map: selected map/mode/team, raw map counts, optional aggregate attributes. Profile stats keys are undocumented (the official example contains stats: {}); support exact known keys and offer observed unknown scalar fields for explicit selection separately, without guessing equivalence or units. Private behavior must be verified with an authorized key later.

Implementation: official transport and tests; endpoint normalization; runtime and entity lifecycle; version-4 configuration migration and per-data options; docs, CI, main and release. No HA restart/deployment.
