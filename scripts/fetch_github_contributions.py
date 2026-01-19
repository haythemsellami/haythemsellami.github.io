#!/usr/bin/env python3
"""
Fetch GitHub organization contributions for a user.
Run once per year to update the contributions data.

Usage:
    export GITHUB_TOKEN=token1,token2,token3
    python scripts/fetch_github_contributions.py

Supports:
    - Multiple tokens (comma-separated) for orgs with different token requirements
    - Manual additions via manual-contributions.json for orgs that block API access

Token requirements:
    - Classic token: 'repo', 'read:org', 'read:user' scopes
    - Fine-grained token: For orgs that block classic tokens, create one per org
      with Repository Contents (read) permission
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("Please install requests: pip install requests")
    sys.exit(1)

GITHUB_USERNAME = "haythemsellami"
GITHUB_API = "https://api.github.com/graphql"
OUTPUT_FILE = Path(__file__).parent.parent / "src" / "data" / "github-contributions.json"
MANUAL_FILE = Path(__file__).parent / "manual-contributions.json"


def get_contributions_for_year(token: str, username: str, year: int) -> list[dict]:
    """Fetch organizations a user contributed to in a given year."""

    from_date = f"{year}-01-01T00:00:00Z"
    to_date = f"{year}-12-31T23:59:59Z"

    query = """
    query($username: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $username) {
        contributionsCollection(from: $from, to: $to) {
          commitContributionsByRepository(maxRepositories: 100) {
            repository {
              owner {
                ... on Organization {
                  login
                  name
                  avatarUrl
                  url
                }
              }
              isPrivate
            }
            contributions {
              totalCount
            }
          }
          pullRequestContributionsByRepository(maxRepositories: 100) {
            repository {
              owner {
                ... on Organization {
                  login
                  name
                  avatarUrl
                  url
                }
              }
              isPrivate
            }
            contributions {
              totalCount
            }
          }
          issueContributionsByRepository(maxRepositories: 100) {
            repository {
              owner {
                ... on Organization {
                  login
                  name
                  avatarUrl
                  url
                }
              }
              isPrivate
            }
            contributions {
              totalCount
            }
          }
        }
      }
    }
    """

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    response = requests.post(
        GITHUB_API,
        json={"query": query, "variables": {"username": username, "from": from_date, "to": to_date}},
        headers=headers,
    )

    if response.status_code != 200:
        return []

    data = response.json()

    if "errors" in data:
        return []

    orgs = {}
    orgs_with_public = set()  # Track orgs with at least one public repo contribution
    collection = data.get("data", {}).get("user", {}).get("contributionsCollection", {})

    contribution_types = [
        "commitContributionsByRepository",
        "pullRequestContributionsByRepository",
        "issueContributionsByRepository",
    ]

    for contrib_type in contribution_types:
        repos = collection.get(contrib_type, [])
        for repo_contrib in repos:
            repo = repo_contrib.get("repository", {})
            owner = repo.get("owner", {})
            login = owner.get("login")

            if not login or not owner.get("avatarUrl"):
                continue
            if login.lower() == username.lower():
                continue

            # Track if this org has public repo contributions
            if not repo.get("isPrivate"):
                orgs_with_public.add(login)

            if login not in orgs:
                orgs[login] = {
                    "login": login,
                    "name": owner.get("name") or login,
                    "avatarUrl": owner.get("avatarUrl"),
                    "url": owner.get("url"),
                }

    # Only return orgs that have at least one public repo contribution
    return [org for org in orgs.values() if org["login"] in orgs_with_public]


def load_manual_contributions() -> dict:
    """Load manual contributions from JSON file."""
    if MANUAL_FILE.exists():
        with open(MANUAL_FILE) as f:
            return json.load(f)
    return {}


def merge_contributions(auto: dict, manual: dict) -> dict:
    """Merge automatic and manual contributions, avoiding duplicates."""
    merged = {}

    all_years = set(auto.keys()) | set(manual.keys())

    for year in all_years:
        auto_orgs = {org["login"]: org for org in auto.get(year, [])}
        manual_orgs = {org["login"]: org for org in manual.get(year, [])}

        # Manual takes precedence (allows overriding names, etc.)
        combined = {**auto_orgs, **manual_orgs}
        merged[year] = list(combined.values())

    return merged


def main():
    token_str = os.environ.get("GITHUB_TOKEN", "")
    tokens = [t.strip() for t in token_str.split(",") if t.strip()]

    if not tokens:
        print("Warning: GITHUB_TOKEN not set, will only use manual contributions")

    current_year = datetime.now().year
    years_to_fetch = range(current_year, 2015, -1)

    all_contributions = {}

    print(f"Fetching contributions for {GITHUB_USERNAME}...")

    for year in years_to_fetch:
        print(f"  {year}...", end=" ")
        year_orgs = {}

        # Try each token and merge results
        for token in tokens:
            orgs = get_contributions_for_year(token, GITHUB_USERNAME, year)
            for org in orgs:
                if org["login"] not in year_orgs:
                    year_orgs[org["login"]] = org

        if year_orgs:
            all_contributions[str(year)] = list(year_orgs.values())
            print(f"found {len(year_orgs)} orgs")
        else:
            all_contributions[str(year)] = []
            print("no orgs found")

    # Load and merge manual contributions
    manual = load_manual_contributions()
    if manual:
        print(f"\nMerging manual contributions from {MANUAL_FILE.name}...")
        all_contributions = merge_contributions(all_contributions, manual)

    # Sort years descending
    all_contributions = dict(sorted(all_contributions.items(), key=lambda x: x[0], reverse=True))

    # Write to file
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w") as f:
        json.dump(all_contributions, f, indent=2)

    print(f"\nSaved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
