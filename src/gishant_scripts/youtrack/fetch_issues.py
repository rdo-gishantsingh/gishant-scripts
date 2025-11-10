import json
from datetime import datetime

import requests


class YouTrackIssuesFetcher:
    """Fetch YouTrack issues where the authenticated user is involved."""

    def __init__(self, base_url: str, token: str):
        """
        Initialize the YouTrack API client.

        Args:
            base_url: Your YouTrack instance URL (e.g., 'https://yourcompany.youtrack.cloud')
            token: Your permanent API token
        """
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_current_user(self) -> dict:
        """Get the current authenticated user's information."""
        url = f"{self.base_url}/api/users/me"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def fetch_issues_where_involved(self, max_results: int = 100) -> list[str]:
        """
        Fetch all issues where the current user is involved (assigned to or commented on).

        Args:
            max_results: Maximum number of issues to fetch (default: 100)

        Returns:
            List of issue IDs
        """
        # Get current user info first
        current_user = self.get_current_user()
        user_login = current_user.get("login", "")

        print(f"Fetching issues for user: {user_login}")

        # Build the query to find issues where you're involved
        # YouTrack query: issues assigned to me OR where I commented
        query = "Assignee: me or commented by: me"

        # API endpoint for searching issues
        url = f"{self.base_url}/api/issues"

        params = {"query": query, "fields": "id,idReadable", "$top": max_results}

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        issues = response.json()

        # Extract just the issue IDs
        issue_ids = [issue.get("idReadable", "") for issue in issues if issue.get("idReadable")]

        return issue_ids

    def fetch_issues_with_details(self, max_results: int = 100) -> list[dict]:
        """
        Fetch all issues where the current user is involved with COMPLETE details.
        Includes description, all comments, all custom fields, and full metadata.

        Args:
            max_results: Maximum number of issues to fetch (default: 100)

        Returns:
            List of issue dictionaries with complete information
        """
        # Get current user info first
        current_user = self.get_current_user()
        user_login = current_user.get("login", "")
        user_full_name = current_user.get("fullName", "")

        print(f"Fetching complete issue data for user: {user_full_name} ({user_login})")

        # Build the query to find issues where you're involved
        query = "Assignee: me or commented by: me"

        # API endpoint for searching issues
        url = f"{self.base_url}/api/issues"

        # Fetch ALL fields including description and all comments
        params = {
            "query": query,
            "fields": "id,idReadable,summary,description,created,updated,"
            "reporter(login,fullName,email),"
            "customFields(name,value(name,fullName,login,text)),"
            "comments(author(login,fullName),text,created,updated,deleted),"
            "tags(name),"
            "links(direction,linkType(name),issues(id,idReadable))",
            "$top": max_results,
        }

        response = requests.get(url, headers=self.headers, params=params)
        response.raise_for_status()

        issues = response.json()

        print(f"Fetched {len(issues)} issues. Processing details...")

        # Process and format the results with ALL data
        results = []
        for idx, issue in enumerate(issues, 1):
            print(f"Processing issue {idx}/{len(issues)}: {issue.get('idReadable', 'N/A')}")

            # Extract custom fields
            custom_fields = {}
            assignee = None
            state = None
            priority = None
            issue_type = None

            for field in issue.get("customFields", []):
                field_name = field.get("name", "")
                value = field.get("value")

                if field_name == "Assignee" and value:
                    assignee = value.get("fullName") or value.get("name", "Unknown")
                    custom_fields["Assignee"] = assignee
                elif field_name == "State" and value:
                    state = value.get("name", "Unknown")
                    custom_fields["State"] = state
                elif field_name == "Priority" and value:
                    priority = value.get("name", "Unknown")
                    custom_fields["Priority"] = priority
                elif field_name == "Type" and value:
                    issue_type = value.get("name", "Unknown")
                    custom_fields["Type"] = issue_type
                elif value:
                    # Store other custom fields
                    if isinstance(value, dict):
                        custom_fields[field_name] = value.get("name") or value.get("text", str(value))
                    else:
                        custom_fields[field_name] = str(value)

            # Get ALL comments (not filtered by user)
            all_comments = []
            user_commented = False

            for comment in issue.get("comments", []):
                if comment.get("deleted"):
                    continue

                author = comment.get("author", {})
                author_login = author.get("login", "Unknown")
                comment_text = comment.get("text", "")

                if author_login == user_login:
                    user_commented = True

                all_comments.append(
                    {
                        "author": author.get("fullName", "Unknown"),
                        "author_login": author_login,
                        "text": comment_text,
                        "created": self._format_timestamp(comment.get("created")),
                        "updated": self._format_timestamp(comment.get("updated")),
                    }
                )

            # Get tags
            tags = [tag.get("name", "") for tag in issue.get("tags", [])]

            # Build comprehensive issue information
            issue_info = {
                "id": issue.get("idReadable", "N/A"),
                "summary": issue.get("summary", "No summary"),
                "description": issue.get("description", "No description"),
                "type": issue_type,
                "state": state,
                "priority": priority,
                "created": self._format_timestamp(issue.get("created")),
                "updated": self._format_timestamp(issue.get("updated")),
                "reporter": issue.get("reporter", {}).get("fullName", "Unknown"),
                "reporter_login": issue.get("reporter", {}).get("login", "Unknown"),
                "assignee": assignee,
                "tags": tags,
                "custom_fields": custom_fields,
                "comments": all_comments,
                "comments_count": len(all_comments),
                "user_commented": user_commented,
                "user_is_assignee": assignee == user_full_name if assignee else False,
                "url": f"{self.base_url}/issue/{issue.get('idReadable', '')}",
            }
            results.append(issue_info)

        return results

    def _format_timestamp(self, timestamp: int) -> str:
        """Convert Unix timestamp (milliseconds) to readable format."""
        if timestamp:
            return datetime.fromtimestamp(timestamp / 1000).strftime("%Y-%m-%d %H:%M:%S")
        return "N/A"

    def print_results(self, issues: list[dict]):
        """Print the issues in a readable format."""
        if not issues:
            print("\nNo issues found where you're involved.")
            return

        print(f"\n{'=' * 80}")
        print(f"Found {len(issues)} issue(s) where you're involved")
        print(f"{'=' * 80}\n")

        for idx, issue in enumerate(issues, 1):
            print(f"{idx}. [{issue['id']}] {issue['summary']}")
            print(
                f"   Type: {issue.get('type', 'N/A')} | State: {issue.get('state', 'N/A')} | Priority: {issue.get('priority', 'N/A')}"
            )
            print(f"   Created: {issue['created']} | Updated: {issue['updated']}")
            print(f"   Reporter: {issue['reporter']}")
            if issue.get("assignee"):
                print(f"   Assignee: {issue['assignee']}")
                if issue.get("user_is_assignee"):
                    print("   ✓ You are assigned to this issue")
            if issue.get("user_commented"):
                print("   ✓ You have commented on this issue")
            print(f"   Total Comments: {issue['comments_count']}")
            if issue.get("tags"):
                print(f"   Tags: {', '.join(issue['tags'])}")
            print(f"   URL: {issue['url']}")

            # Print description preview
            if issue.get("description"):
                desc_preview = (
                    issue["description"][:150] + "..." if len(issue["description"]) > 150 else issue["description"]
                )
                print(f"   Description: {desc_preview}")

            print()

    def print_issue_ids(self, issue_ids: list[str]):
        """Print just the issue IDs."""
        if not issue_ids:
            print("\nNo issues found where you're involved.")
            return

        print(f"\nFound {len(issue_ids)} issue(s) where you're involved:\n")
        for issue_id in issue_ids:
            print(issue_id)

    def save_to_json(self, issues: list[dict], filename: str = "my_youtrack_issues.json"):
        """Save the results to a JSON file."""
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)
        print(f"\nResults saved to {filename}")

    def save_ids_to_file(self, issue_ids: list[str], filename: str = "my_youtrack_issue_ids.txt"):
        """Save just the issue IDs to a text file."""
        with open(filename, "w", encoding="utf-8") as f:
            for issue_id in issue_ids:
                f.write(f"{issue_id}\n")
        print(f"\nIssue IDs saved to {filename}")


def main():
    """Main entry point for fetching YouTrack issues.

    Requires environment variables:
        YOUTRACK_URL: Your YouTrack instance URL
        YOUTRACK_API_TOKEN: Your API token

    Configuration can be provided via:
        - .env file in current directory
        - ~/.gishant_scripts.env file
        - Direct environment variables
    """
    from gishant_scripts.common.config import AppConfig
    from gishant_scripts.common.errors import ConfigurationError

    # Load configuration
    try:
        config = AppConfig()
        config.require_valid("youtrack")
    except ConfigurationError as err:
        print(f"❌ Configuration Error: {err}")
        print("\n💡 Set up your .env file with:")
        print("  YOUTRACK_URL=https://your-instance.youtrack.cloud")
        print("  YOUTRACK_API_TOKEN=perm-your-token-here")
        print("\nYou can copy .env.example to .env and fill in your values.")
        return 1

    # Initialize the fetcher
    fetcher = YouTrackIssuesFetcher(config.youtrack.url, config.youtrack.api_token)

    try:
        # Fetch detailed issue information
        print("Fetching detailed issue information...")
        issues = fetcher.fetch_issues_with_details(max_results=200)

        # Display results
        fetcher.print_results(issues)

        # Save to JSON file
        fetcher.save_to_json(issues)

        # Extract and save just the issue IDs
        issue_ids = [issue["id"] for issue in issues]
        fetcher.save_ids_to_file(issue_ids)

        print(f"\n✅ Successfully fetched {len(issues)} issues")
        print("📄 Detailed data saved to: my_youtrack_issues.json")
        print("📋 Issue IDs saved to: my_youtrack_issue_ids.txt")
        return 0

    except requests.exceptions.HTTPError as err:
        print(f"❌ HTTP Error: {err}")
        print(f"Response: {err.response.text}")
        return 1
    except Exception as err:
        print(f"❌ Error: {err}")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
