"""Vuis HTML normalization keeps the requested public data scope."""

from custom_components.blockfront.vuis import (
    parse_brigade,
    parse_brigade_scoreboard,
    parse_match_detail,
    parse_matches,
    parse_profile,
)

UUID = "85c194ce-8ae5-4736-bf14-7e9bdd204c66"
MATCH_ID = "da773e7c-a124-4fed-9ca7-d42d257a5cc3"


def test_profile_numbers_rank_progress_classes_and_player_uuid():
    classes = "".join(
        f"<tr><td>{name}</td><td>{value:,}</td></tr>"
        for name, value in (
            ("Rifleman", 1208),
            ("Lt. Rifle", 1808),
            ("Assault", 1982),
            ("Support", 49),
            ("Medic", 10),
            ("Sniper", 6659),
            ("Gunner", 358),
            ("Anti-Tank", 46),
        )
    )
    page = f"""
      <h1>Stats for player denkz0ne</h1>
      <img src="/avatars/{UUID}.png">
      <div>Rank: <span>Lt. Colonel</span></div>
      <div>Skill Rank: <span>Iron Master</span></div>
      <div>EXP: <span>133,320</span></div>
      <div>Games: <span>330</span></div>
      <div>K/D: <span>0.87</span></div>
      <div>Wins: <span>57</span></div>
      <div>Time Played: <span>108.8h</span></div>
      <div>EXP Progress: <span>10,319</span> / <span>22,000</span></div>
      <div>EXP Remaining: <span>11,681</span></div>
      <div>Prestige Level: <span>0</span></div>
      <div>Completed Bootcamp: <span>Yes</span></div>
      <a href="/bfstats/brigades/VAH">[VAH]</a>
      <table><tr><th>Class</th><th>EXP</th></tr>{classes}</table>
    """
    values, attrs = parse_profile(page)
    assert attrs["player_uuid"] == UUID
    assert values["rank"] == "Lt. Colonel"
    assert values["skill_rank"] == "Iron Master"
    assert values["exp"] == 133320
    assert values["time_played"] == 391680
    assert values["rank_exp_progress"] == 10319
    assert values["rank_exp_required"] == 22000
    assert values["rank_exp_remaining"] == 11681
    assert values["rank_progress_percent"] == 100 * 10319 / 22000
    assert values["win_rate"] == 100 * 57 / 330
    assert values["class_exp"] == 12120
    assert values["class_exp_lieutenant_rifle"] == 1808
    assert values["bootcamp"] is True
    assert "captures" not in values
    assert "commander_exp" not in values


def test_latest_match_reads_personal_line_and_team_totals_only():
    matches_page = f"""
      <h1>Matches for player denkz0ne</h1>
      <table>
        <tr>
          <th>Player</th><th>Game</th><th>Map</th><th>Result</th><th>Team</th>
          <th>Ended</th><th>Place</th><th>Kills</th><th>Deaths</th><th>Assists</th><th>Score</th>
        </tr>
        <tr><td>denkz0ne</td><td>DOM</td><td>Storm</td><td>LOSS</td><td>Allies</td>
        <td>19h ago</td><td>#9</td><td>7</td><td>10</td><td>3</td><td>20</td></tr>
      </table>
      <a href="/bfstats/match/{MATCH_ID}">match</a>
    """
    values, attrs, match_id = parse_matches(matches_page, "denkz0ne")
    assert match_id == MATCH_ID
    assert values["latest_match"] == "loss"
    assert values["latest_match_map"] == "Storm"
    assert values["latest_match_score"] == 20
    assert values["latest_match_kills"] == 7
    assert values["latest_match_deaths"] == 10
    assert values["latest_match_assists"] == 3
    assert values["latest_match_placement"] == 9
    assert values["latest_match_end"] is None
    assert attrs["latest_match_relative_time"] == "19h ago"

    detail = """
      <p>Score: 347 - 400</p>
      <p>Date: 16 Nov 2026 17:09:04 UTC</p>
      <h2>Allies (20) 347</h2><h2>Axis (20) 400</h2>
      <table><tr><th>Player</th><th>Kills</th></tr><tr><td>denkz0ne</td><td>7</td></tr></table>
    """
    totals = parse_match_detail(detail)
    assert totals["latest_match_allies_score"] == 347
    assert totals["latest_match_axis_score"] == 400
    assert totals["latest_match_end"].isoformat() == "2026-11-16T17:09:04+00:00"
    assert not any("player" in key.casefold() for key in totals)


def test_brigade_pages_return_player_role_and_one_scoreboard_row():
    brigade = """
      <h2>OSSR Slovakia</h2><h3>[VAH]</h3>
      <p>128/128 members</p>
      <table><tr><th>Member</th><th>Role</th></tr>
        <tr><td>denkz0ne</td><td>Member</td></tr>
        <tr><td>anotherPlayer</td><td>Leader</td></tr>
      </table>
    """
    values = parse_brigade(brigade, "VAH", "denkz0ne")
    assert values["brigade_name"] == "OSSR Slovakia"
    assert values["brigade_tag"] == "VAH"
    assert values["brigade_member_count"] == 128
    assert values["brigade_capacity"] == 128
    assert values["brigade_role"] == "Member"

    scoreboard = """
      <table><tr><th>Rank</th><th>Name</th><th>Score</th></tr>
        <tr><td>#2</td><td>VAH</td><td>46,280</td></tr>
        <tr><td>#3</td><td>OTHER</td><td>20,000</td></tr>
      </table>
    """
    assert parse_brigade_scoreboard(scoreboard, "VAH") == {
        "brigade_rank": 2,
        "brigade_score": 46280,
    }
