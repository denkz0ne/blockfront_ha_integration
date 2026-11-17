"""Public Vuis pages used as the primary BlockFront player data source."""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, datetime
from html.parser import HTMLParser
from time import monotonic
from urllib.parse import quote

import aiohttp

BASE_URL = "https://vuis.dev/bfstats/"
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{3,16}$")
UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
CLASS_KEYS = {
    "rifleman": "rifleman",
    "lt. rifle": "lieutenant_rifle",
    "assault": "assault",
    "support": "support",
    "medic": "medic",
    "sniper": "sniper",
    "gunner": "gunner",
    "anti-tank": "anti_tank",
}


class VuisError(Exception):
    """A public Vuis page could not be fetched or parsed."""


class _PageParser(HTMLParser):
    """Collect page text, simple table rows, links, and image sources."""

    _BLOCKS = {"div", "p", "h1", "h2", "h3", "h4", "li", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.text_parts = []
        self.tables = []
        self.links = []
        self.images = []
        self._table = None
        self._row = None
        self._cell = None
        self._link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in self._BLOCKS or tag == "br":
            self.text_parts.append("\n")
        if tag == "table":
            self._table = []
        elif tag == "tr" and self._table is not None:
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "a":
            self._link = {"href": attrs.get("href", ""), "text": []}
        elif tag == "img":
            self.images.append(attrs.get("src", ""))

    def handle_endtag(self, tag):
        if tag in self._BLOCKS or tag in {"td", "th"}:
            self.text_parts.append("\n")
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None and self._table is not None:
            self._table.append(self._row)
            self._row = None
        elif tag == "table" and self._table is not None:
            self.tables.append(self._table)
            self._table = None
        elif tag == "a" and self._link is not None:
            self._link["text"] = "".join(self._link["text"]).strip()
            self.links.append(self._link)
            self._link = None

    def handle_data(self, data):
        self.text_parts.append(data)
        if self._cell is not None:
            self._cell.append(data)
        if self._link is not None:
            self._link["text"].append(data)

    @property
    def lines(self):
        result = []
        for line in "".join(self.text_parts).splitlines():
            line = " ".join(line.split())
            if line:
                result.append(line)
        return result


class VuisClient:
    """A small, serialized, credential-free client for public Vuis pages."""

    def __init__(self, session):
        self.session = session
        self._lock = asyncio.Lock()
        self._next_request = 0.0

    async def get(self, path):
        path = path.lstrip("/")
        url = BASE_URL + path
        async with self._lock:
            await asyncio.sleep(max(0, self._next_request - monotonic()))
            self._next_request = monotonic() + 0.5
            try:
                async with self.session.get(
                    url,
                    timeout=aiohttp.ClientTimeout(total=20),
                    allow_redirects=False,
                    headers={"Accept": "text/html"},
                ) as response:
                    if response.status == 404:
                        raise VuisError("Player or public statistics page was not found")
                    if response.status != 200:
                        raise VuisError(f"Vuis returned HTTP {response.status}")
                    if response.content_length and response.content_length > 2_000_000:
                        raise VuisError("Vuis page is unexpectedly large")
                    body = await response.text()
            except (TimeoutError, aiohttp.ClientError, UnicodeError) as err:
                raise VuisError("Could not read the public Vuis statistics page") from err
        return body


def validate_username(username):
    """Return a validated Minecraft username or raise ValueError."""
    if not isinstance(username, str) or not USERNAME_RE.fullmatch(username.strip()):
        raise ValueError("Invalid Minecraft username")
    return username.strip()


def _parse_page(source):
    parser = _PageParser()
    parser.feed(source)
    parser.close()
    return parser


def _number(value):
    if value is None:
        return None
    match = re.fullmatch(r"\s*([+-]?(?:\d[\d,]*)(?:\.\d+)?)\s*", str(value))
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def _integer(value):
    number = _number(value)
    return int(number) if number is not None and number.is_integer() else None


def _field(lines, label):
    prefix = f"{label}:"
    for line in lines:
        if line.casefold().startswith(prefix.casefold()):
            return line[len(prefix) :].strip()
    return None


def _timestamp(value):
    match = re.search(
        r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})\s+"
        r"(\d{2}:\d{2}:\d{2})\s+UTC",
        value or "",
    )
    if not match:
        return None
    months = {
        "jan": 1,
        "feb": 2,
        "mar": 3,
        "apr": 4,
        "may": 5,
        "jun": 6,
        "jul": 7,
        "aug": 8,
        "sep": 9,
        "oct": 10,
        "nov": 11,
        "dec": 12,
    }
    month = months.get(match.group(2).casefold())
    if month is None:
        return None
    try:
        return datetime.strptime(
            f"{match.group(3)}-{month:02d}-{int(match.group(1)):02d} {match.group(4)}",
            "%Y-%m-%d %H:%M:%S",
        ).replace(tzinfo=UTC)
    except ValueError:
        return None


def parse_profile(source, expected_uuid=None):
    """Normalize one public Vuis player stats page."""
    page = _parse_page(source)
    text = "\n".join(page.lines)
    name_match = re.search(r"Stats for player\s+([A-Za-z0-9_]{3,16})", text)
    if not name_match:
        raise VuisError("Vuis did not return a player profile")
    username = name_match.group(1)
    raw_uuid = next((UUID_RE.search(src) for src in page.images if UUID_RE.search(src)), None)
    identity = raw_uuid.group(0).lower() if raw_uuid else None
    if identity is None:
        raise VuisError("Vuis profile does not expose a player UUID")
    if expected_uuid and identity != expected_uuid.lower():
        raise VuisError("Vuis profile username now points to a different player")

    values = {
        "username": username,
        "rank": _field(page.lines, "Rank"),
        "skill_rank": _field(page.lines, "Skill Rank"),
        "exp": _integer(_field(page.lines, "EXP")),
        "match_karma": _integer(_field(page.lines, "Match Karma")),
        "total_games": _integer(_field(page.lines, "Games")),
        "kd_ratio": _number(_field(page.lines, "K/D")),
        "head_shots": _integer(_field(page.lines, "Headshots")),
        "kills": _integer(_field(page.lines, "Kills")),
        "kill_streak": _integer(_field(page.lines, "Kill Streak")),
        "fire_kills": _integer(_field(page.lines, "Fire Kills")),
        "back_stabs": _integer(_field(page.lines, "Back-stabs")),
        "assists": _integer(_field(page.lines, "Assists")),
        "heal_assists": _integer(_field(page.lines, "Heal Assists")),
        "no_scopes": _integer(_field(page.lines, "No-scopes")),
        "deaths": _integer(_field(page.lines, "Deaths")),
        "death_streak": _integer(_field(page.lines, "Death Streak")),
        "first_bloods": _integer(_field(page.lines, "First-bloods")),
        "wins": _integer(_field(page.lines, "Wins")),
        "prestige": _integer(_field(page.lines, "Prestige Level")),
        "objective_score": _integer(_field(page.lines, "Objective Score")),
        "infected_rounds_won": _integer(_field(page.lines, "Infected Rounds Won")),
        "infected_matches_won": _integer(_field(page.lines, "Infected Matches Won")),
        "bot_kills": _integer(_field(page.lines, "Bot Kills")),
        "infected_kills": _integer(_field(page.lines, "Infected Kills")),
        "vehicle_kills": _integer(_field(page.lines, "Vehicle Kills")),
    }
    played = _field(page.lines, "Time Played")
    played_match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*h\s*", played or "", re.I)
    values["time_played"] = (
        round(float(played_match.group(1)) * 3600) if played_match else None
    )
    progress = _field(page.lines, "EXP Progress")
    progress_match = re.fullmatch(r"\s*([\d,]+)\s*/\s*([\d,]+)\s*", progress or "")
    values["rank_exp_progress"] = _integer(progress_match.group(1)) if progress_match else None
    values["rank_exp_required"] = _integer(progress_match.group(2)) if progress_match else None
    values["rank_exp_remaining"] = _integer(_field(page.lines, "EXP Remaining"))
    needed = values["rank_exp_required"]
    values["rank_progress_percent"] = (
        min(100, max(0, 100 * values["rank_exp_progress"] / needed))
        if needed and values["rank_exp_progress"] is not None
        else None
    )
    games = values["total_games"]
    wins = values["wins"]
    values["win_rate"] = 100 * wins / games if games and wins is not None else None
    bootcamp = _field(page.lines, "Completed Bootcamp")
    values["bootcamp"] = (
        bootcamp.casefold() == "yes" if bootcamp and bootcamp.casefold() in {"yes", "no"} else None
    )

    brigade_link = next(
        (
            link
            for link in page.links
            if link["href"].startswith("/bfstats/brigades/")
        ),
        None,
    )
    values["brigade_tag"] = (
        brigade_link["href"].rsplit("/", 1)[-1] if brigade_link else None
    )
    class_exp = {}
    for table in page.tables:
        if not table or [c.casefold() for c in table[0]] != ["class", "exp"]:
            continue
        for row in table[1:]:
            if len(row) < 2:
                continue
            class_key = CLASS_KEYS.get(row[0].strip().casefold())
            amount = _integer(row[1])
            if class_key and amount is not None:
                class_exp[class_key] = amount
    for key, amount in class_exp.items():
        values[f"class_exp_{key}"] = amount
    values["class_exp"] = (
        sum(class_exp.values()) if len(class_exp) == len(CLASS_KEYS) else None
    )
    if not any(values.get(key) is not None for key in ("exp", "kills", "total_games")):
        raise VuisError("Vuis player profile did not contain recognizable statistics")
    attrs = {
        "source": "vuis.dev",
        "player_uuid": identity,
        "username": username,
        "brigade_tag": values["brigade_tag"],
        "time_played_precision_hours": 0.1,
        "time_played_is_rounded": values["time_played"] is not None,
        "class_exp_available": sorted(class_exp),
        "exp": values["exp"],
        "rank": values["rank"],
        "skill_rank": values["skill_rank"],
        "rank_exp_progress": values["rank_exp_progress"],
        "rank_exp_required": values["rank_exp_required"],
        "rank_exp_remaining": values["rank_exp_remaining"],
        "rank_progress_percent": values["rank_progress_percent"],
        "win_rate": values["win_rate"],
    }
    return values, attrs


def parse_matches(source, expected_username):
    """Read the newest row from a player's public matches table."""
    page = _parse_page(source)
    table = next(
        (
            rows
            for rows in page.tables
            if rows and [cell.casefold() for cell in rows[0]][1:]
            == [
                "game",
                "map",
                "result",
                "team",
                "ended",
                "place",
                "kills",
                "deaths",
                "assists",
                "score",
            ]
        ),
        None,
    )
    if not table or len(table) < 2:
        raise VuisError("Vuis did not return the player matches table")
    expected_title = f"Matches for player {expected_username}".casefold()
    if not any(line.casefold() == expected_title for line in page.lines):
        raise VuisError("Vuis matches page belongs to a different player")
    headers = [cell.casefold() for cell in table[0]]
    row = table[1]
    if len(row) != len(headers):
        raise VuisError("Vuis returned an incomplete latest match row")
    fields = dict(zip(headers, row, strict=False))
    detail = next(
        (
            link["href"]
            for link in page.links
            if link["href"].startswith("/bfstats/match/")
        ),
        None,
    )
    match = UUID_RE.search(detail or "")
    match_id = match.group(0).lower() if match else None
    result = fields.get("result", "").casefold()
    place = re.fullmatch(r"#\s*(\d+)", fields.get("place", ""))
    values = {
        "latest_match": result if result in {"win", "loss", "draw"} else fields.get("result"),
        "latest_match_score": _integer(fields.get("score")),
        "latest_match_kills": _integer(fields.get("kills")),
        "latest_match_deaths": _integer(fields.get("deaths")),
        "latest_match_assists": _integer(fields.get("assists")),
        "latest_match_placement": int(place.group(1)) if place else None,
        "latest_match_mode": fields.get("game"),
        "latest_match_map": fields.get("map"),
        "latest_match_team": fields.get("team"),
        "latest_match_end": None,
        "latest_match_allies_score": None,
        "latest_match_axis_score": None,
    }
    return values, {
        "source": "vuis.dev",
        "latest_match_id": match_id,
        "latest_match_relative_time": fields.get("ended"),
        "latest_match_detail_available": bool(match_id),
    }, match_id


def parse_match_detail(source):
    """Extract only the date and two team totals, never the player roster."""
    page = _parse_page(source)
    text = "\n".join(page.lines)
    score_match = re.search(r"\bScore:\s*(\d+)\s*[-–]\s*(\d+)\b", text)
    date_match = re.search(
        r"\bDate:\s*(\d{1,2}\s+[A-Za-z]{3}\s+\d{4}\s+"
        r"\d{2}:\d{2}:\d{2}\s+UTC)",
        text,
    )
    team_order = []
    for line in page.lines:
        team = re.match(r"(Allies|Axis)\s+\(\d+\)(?:\s+\d+)?$", line)
        if team:
            team_order.append(team.group(1))
    first, second = (int(score_match.group(i)) for i in (1, 2)) if score_match else (None, None)
    if team_order[:2] == ["Allies", "Axis"]:
        allies_score, axis_score = first, second
    elif team_order[:2] == ["Axis", "Allies"]:
        allies_score, axis_score = second, first
    else:
        allies_score, axis_score = None, None
    return {
        "latest_match_allies_score": allies_score,
        "latest_match_axis_score": axis_score,
        "latest_match_end": _timestamp(date_match.group(1)) if date_match else None,
        "latest_match_score_team_order": team_order[:2],
    }


def parse_brigade(source, tag, username):
    """Read brigade summary and only the configured player's role."""
    page = _parse_page(source)
    text = "\n".join(page.lines)
    header = next(
        (line for line in page.lines if re.fullmatch(r"\[" + re.escape(tag) + r"\]", line)),
        None,
    )
    count_match = re.search(r"(\d+)\s*/\s*(\d+)\s+members\b", text, re.I)
    values = {
        "brigade_name": None,
        "brigade_tag": tag,
        "brigade_member_count": int(count_match.group(1)) if count_match else None,
        "brigade_capacity": int(count_match.group(2)) if count_match else None,
        "brigade_role": None,
    }
    if header:
        header_index = page.lines.index(header)
        if header_index:
            values["brigade_name"] = page.lines[header_index - 1]
    for table in page.tables:
        if not table or [cell.casefold() for cell in table[0]][:2] != ["member", "role"]:
            continue
        for row in table[1:]:
            if len(row) >= 2 and row[0].casefold() == username.casefold():
                values["brigade_role"] = row[1]
                break
    return values


def parse_brigade_scoreboard(source, tag):
    """Find one brigade's rank and score without creating a scoreboard entity."""
    page = _parse_page(source)
    for table in page.tables:
        if not table or [cell.casefold() for cell in table[0]][:3] != ["rank", "name", "score"]:
            continue
        for row in table[1:]:
            if len(row) < 3 or row[1].strip().casefold() != tag.casefold():
                continue
            rank = re.fullmatch(r"#\s*(\d+)", row[0].strip())
            return {
                "brigade_rank": int(rank.group(1)) if rank else None,
                "brigade_score": _integer(row[2]),
            }
    return {"brigade_rank": None, "brigade_score": None}


async def resolve_player(session, username):
    """Look up a player's UUID from the public profile page."""
    username = validate_username(username)
    client = VuisClient(session)
    page = await client.get(f"players/{quote(username, safe='')}/stats")
    values, attrs = parse_profile(page)
    return values["username"], attrs["player_uuid"]
