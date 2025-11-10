"""
Fetch GitHub Pull Requests assigned to the authenticated user.
Uses GitHub CLI to retrieve PR details.
"""

import json
import subprocess
import sys
from datetime import datetime
from typing import Any


class GitHubPRFetcher:
    """Fetch GitHub Pull Requests using GitHub CLI."""

    def __init__(self):
        self.user_login = None

    def check_gh_cli(self) -> bool:
        """Check if GitHub CLI is installed and authenticated."""
        try:
            result = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
            return result.returncode == 0
        except FileNotFoundError:
            print("❌ GitHub CLI (gh) is not installed!")
            print("Install it from: https://cli.github.com/")
            return False

    def get_current_user(self) -> str:
        """Get the authenticated GitHub user."""
        try:
            result = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True, check=True)
            self.user_login = result.stdout.strip()
            return self.user_login
        except subprocess.CalledProcessError as e:
            print(f"❌ Error getting user info: {e}")
            return None

    def fetch_user_prs(self, limit: int = 100) -> list[dict[str, Any]]:
        """
        Fetch PRs where user is author or assignee.

        Args:
            limit: Maximum number of PRs to fetch

        Returns:
            List of PR details
        """
        if not self.user_login:
            self.get_current_user()

        print(f"\n🔍 Searching for PRs by @{self.user_login}...")

        # Fetch PRs authored by user
        prs_data = []

        # Search for PRs across all repos the user has access to
        try:
            # Get authored PRs (open)
            print("  → Fetching open PRs you authored...")
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "prs",
                    f"--author={self.user_login}",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,title,state,url,repository,createdAt,updatedAt,closedAt,author,assignees,body,labels,commentsCount,isDraft",
                    "--state",
                    "open",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            authored_prs = json.loads(result.stdout)
            print(f"  ✓ Found {len(authored_prs)} open authored PRs")
            prs_data.extend(authored_prs)

            # Get authored PRs (closed)
            print("  → Fetching closed PRs you authored...")
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "prs",
                    f"--author={self.user_login}",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,title,state,url,repository,createdAt,updatedAt,closedAt,author,assignees,body,labels,commentsCount,isDraft",
                    "--state",
                    "closed",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            closed_prs = json.loads(result.stdout)
            print(f"  ✓ Found {len(closed_prs)} closed authored PRs")
            prs_data.extend(closed_prs)

            # Get assigned PRs (open) not already in list
            print("  → Fetching open PRs assigned to you...")
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "prs",
                    f"--assignee={self.user_login}",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,title,state,url,repository,createdAt,updatedAt,closedAt,author,assignees,body,labels,commentsCount,isDraft",
                    "--state",
                    "open",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            assigned_prs_open = json.loads(result.stdout)
            existing_urls = {pr["url"] for pr in prs_data}
            new_assigned = [pr for pr in assigned_prs_open if pr["url"] not in existing_urls]
            print(f"  ✓ Found {len(new_assigned)} additional open assigned PRs")
            prs_data.extend(new_assigned)

            # Get assigned PRs (closed) not already in list
            print("  → Fetching closed PRs assigned to you...")
            result = subprocess.run(
                [
                    "gh",
                    "search",
                    "prs",
                    f"--assignee={self.user_login}",
                    "--limit",
                    str(limit),
                    "--json",
                    "number,title,state,url,repository,createdAt,updatedAt,closedAt,author,assignees,body,labels,commentsCount,isDraft",
                    "--state",
                    "closed",
                ],
                capture_output=True,
                text=True,
                check=True,
            )

            assigned_prs_closed = json.loads(result.stdout)
            existing_urls = {pr["url"] for pr in prs_data}
            new_assigned_closed = [pr for pr in assigned_prs_closed if pr["url"] not in existing_urls]

            print(f"  ✓ Found {len(new_assigned_closed)} additional closed assigned PRs")
            prs_data.extend(new_assigned_closed)

        except subprocess.CalledProcessError as e:
            print(f"❌ Error fetching PRs: {e}")
            print(f"stderr: {e.stderr}")
            return []
        except json.JSONDecodeError as e:
            print(f"❌ Error parsing PR data: {e}")
            return []

        # Process and enrich the data
        print(f"\n📊 Processing {len(prs_data)} PRs...")
        processed_prs = []
        for i, pr in enumerate(prs_data, 1):
            repo_name = pr.get("repository", {}).get("nameWithOwner", "Unknown")
            pr_number = pr.get("number")

            # Get detailed PR info for additions/deletions/files
            pr_details = self._get_pr_details(repo_name, pr_number)

            is_merged = pr.get("state") == "MERGED" or (pr.get("closedAt") and "merged" in pr.get("body", "").lower())

            processed_pr = {
                "number": pr_number,
                "title": pr.get("title"),
                "state": pr.get("state"),
                "url": pr.get("url"),
                "repository": repo_name,
                "created_at": self._format_timestamp(pr.get("createdAt")),
                "updated_at": self._format_timestamp(pr.get("updatedAt")),
                "closed_at": self._format_timestamp(pr.get("closedAt")) if pr.get("closedAt") else None,
                "merged_at": "Merged" if is_merged else None,
                "additions": pr_details.get("additions", 0),
                "deletions": pr_details.get("deletions", 0),
                "changed_files": pr_details.get("changedFiles", 0),
                "author": pr.get("author", {}).get("login", "Unknown"),
                "assignees": [a.get("login") for a in pr.get("assignees", [])],
                "review_decision": pr_details.get("reviewDecision"),
                "comments_count": pr.get("commentsCount", 0),
                "reviews_count": 0,  # Not available in search
                "labels": [l.get("name") for l in pr.get("labels", [])],
                "is_draft": pr.get("isDraft", False),
                "is_author": pr.get("author", {}).get("login") == self.user_login,
                "is_assignee": self.user_login in [a.get("login") for a in pr.get("assignees", [])],
            }
            processed_prs.append(processed_pr)

            if i % 10 == 0:
                print(f"  ✓ Processed {i}/{len(prs_data)} PRs...")

        return processed_prs

    def _get_pr_details(self, repo: str, pr_number: int) -> dict:
        """Get detailed PR information including additions/deletions."""
        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "view",
                    str(pr_number),
                    "-R",
                    repo,
                    "--json",
                    "additions,deletions,changedFiles,reviewDecision",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
        return {}

    def _format_timestamp(self, timestamp: str) -> str:
        """Convert ISO timestamp to readable format."""
        if not timestamp:
            return "N/A"
        try:
            dt = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, AttributeError):
            return timestamp

    def print_results(self, prs: list[dict[str, Any]]):
        """Print PR results to console."""
        print("\n" + "=" * 100)
        print(f"FOUND {len(prs)} PULL REQUESTS")
        print("=" * 100)

        for pr in prs:
            print(f"\n{'=' * 100}")
            print(f"PR #{pr['number']}: {pr['title']}")
            print(f"{'=' * 100}")
            print(f"Repository:       {pr['repository']}")
            print(f"State:            {pr['state']}")
            print(f"Review Decision:  {pr['review_decision'] or 'N/A'}")
            print(f"Author:           {pr['author']}")
            print(f"Assignees:        {', '.join(pr['assignees']) if pr['assignees'] else 'None'}")
            print(f"Created:          {pr['created_at']}")
            print(f"Updated:          {pr['updated_at']}")
            if pr["merged_at"]:
                print(f"Merged:           {pr['merged_at']}")
            if pr["closed_at"]:
                print(f"Closed:           {pr['closed_at']}")
            print(f"Changes:          +{pr['additions']} -{pr['deletions']} ({pr['changed_files']} files)")
            print(f"Comments:         {pr['comments_count']}")
            print(f"Reviews:          {pr['reviews_count']}")
            print(f"URL:              {pr['url']}")
            print(f"Is Author:        {pr['is_author']}")
            print(f"Is Assignee:      {pr['is_assignee']}")

    def save_to_json(self, prs: list[dict[str, Any]], filename: str = "my_github_prs.json"):
        """Save PRs to JSON file."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(prs, f, indent=2, ensure_ascii=False)
        print(f"\n✅ Saved {len(prs)} PRs to {filename}")


def main():
    """Main function to fetch GitHub PRs."""
    print("=" * 100)
    print("GITHUB PULL REQUESTS FETCHER")
    print("=" * 100)

    fetcher = GitHubPRFetcher()

    # Check if gh CLI is available
    if not fetcher.check_gh_cli():
        sys.exit(1)

    # Get current user
    print("\n📋 Getting authenticated user...")
    user = fetcher.get_current_user()
    if not user:
        print("❌ Could not get authenticated user")
        sys.exit(1)

    print(f"✓ Authenticated as: {user}")

    # Fetch PRs
    prs = fetcher.fetch_user_prs(limit=100)

    if not prs:
        print("\n⚠️  No pull requests found")
        return

    # Print results
    fetcher.print_results(prs)

    # Save to JSON
    fetcher.save_to_json(prs)

    print(f"\n{'=' * 100}")
    print(f"✅ SUCCESS! Fetched {len(prs)} pull requests")
    print(f"📊 Authored: {sum(1 for pr in prs if pr['is_author'])}")
    print(f"📊 Assigned: {sum(1 for pr in prs if pr['is_assignee'])}")
    print(f"📊 Merged: {sum(1 for pr in prs if pr['merged_at'])}")
    print(f"📊 Open: {sum(1 for pr in prs if pr['state'] == 'OPEN')}")
    print(f"{'=' * 100}")


if __name__ == "__main__":
    main()
