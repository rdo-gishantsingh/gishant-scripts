"""
Generate Management Report Email from YouTrack Issues and GitHub PRs
Uses Gemini AI to create a professional summary of work contributions.
"""

import json
import os
from datetime import datetime

from google import genai

# Available Gemini models
AVAILABLE_MODELS = [
    "gemini-2.5-pro",
    "gemini-2.5-flash",
]


def load_issues_data(json_file: str = "my_youtrack_issues.json") -> list:
    """Load issues data from JSON file."""
    with open(json_file, encoding="utf-8") as f:
        return json.load(f)


def load_github_prs(json_file: str = "my_github_prs.json") -> list:
    """Load GitHub PRs data from JSON file."""
    if not os.path.exists(json_file):
        print(f"⚠️  GitHub PRs file not found: {json_file}")
        return []

    try:
        with open(json_file, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading GitHub PRs: {e}")
        return []


def prepare_summary_data(issues: list, prs: list = None):
    """Prepare a summarized version of issues and PRs for the AI."""
    # Categorize issues - check both boolean flags and actual data
    assigned_issues = [
        i
        for i in issues
        if (i.get("user_is_assignee") or (i.get("assignee") and "gishant" in i.get("assignee", "").lower()))
    ]

    # Issues where user commented (check both flag and actual comments)
    user_commented_in = []
    for issue in issues:
        if issue.get("user_commented"):
            user_commented_in.append(issue)
        elif any(c.get("author_login") == "gisi" for c in issue.get("comments", [])):
            user_commented_in.append(issue)

    commented_issues = [i for i in user_commented_in if i not in assigned_issues]

    # Count by state
    states = {}
    types = {}
    priorities = {}

    for issue in assigned_issues:
        state = issue.get("state", "Unknown")
        issue_type = issue.get("type", "Unknown")
        priority = issue.get("priority", "Unknown")

        states[state] = states.get(state, 0) + 1
        types[issue_type] = types.get(issue_type, 0) + 1
        priorities[priority] = priorities.get(priority, 0) + 1

    summary = {
        "total_issues": len(issues),
        "assigned_issues": len(assigned_issues),
        "commented_issues": len(commented_issues),
        "states": states,
        "types": types,
        "priorities": priorities,
        "issues_detail": [],
    }

    # Add issue details for the AI to understand context
    for issue in assigned_issues:
        issue_info = {
            "id": issue["id"],
            "summary": issue["summary"],
            "type": issue.get("type", "N/A"),
            "state": issue.get("state", "N/A"),
            "priority": issue.get("priority", "N/A"),
            "description_preview": issue.get("description", "")[:200],  # First 200 chars
            "comments_count": issue.get("comments_count", 0),
            "created": issue.get("created", ""),
            "updated": issue.get("updated", ""),
        }
        summary["issues_detail"].append(issue_info)

    # Also include issues where user provided significant input via comments
    for issue in commented_issues[:10]:  # Limit to 10 most relevant
        issue_info = {
            "id": issue["id"],
            "summary": issue["summary"],
            "type": issue.get("type", "N/A"),
            "state": issue.get("state", "N/A"),
            "contribution": "Provided technical guidance and support via comments",
            "comments_count": issue.get("comments_count", 0),
        }
        summary["issues_detail"].append(issue_info)

    # Add GitHub PR data if available
    if prs:
        pr_states = {}
        pr_repos = {}

        for pr in prs:
            state = pr.get("state", "Unknown")
            repo = pr.get("repository", "Unknown")

            pr_states[state] = pr_states.get(state, 0) + 1
            pr_repos[repo] = pr_repos.get(repo, 0) + 1

        summary["github_prs"] = {
            "total_prs": len(prs),
            "authored": sum(1 for pr in prs if pr.get("is_author")),
            "assigned": sum(1 for pr in prs if pr.get("is_assignee")),
            "merged": sum(1 for pr in prs if pr.get("merged_at")),
            "open": sum(1 for pr in prs if pr.get("state") == "OPEN"),
            "states": pr_states,
            "repositories": pr_repos,
            "prs_detail": [],
        }

        # Add PR details
        for pr in prs[:20]:  # Limit to 20 most relevant
            pr_info = {
                "number": pr.get("number"),
                "title": pr.get("title"),
                "repository": pr.get("repository"),
                "state": pr.get("state"),
                "review_decision": pr.get("review_decision"),
                "additions": pr.get("additions", 0),
                "deletions": pr.get("deletions", 0),
                "changed_files": pr.get("changed_files", 0),
                "created_at": pr.get("created_at"),
                "merged_at": pr.get("merged_at"),
                "is_author": pr.get("is_author"),
            }
            summary["github_prs"]["prs_detail"].append(pr_info)

    return summary


def generate_email_with_gemini(
    summary_data: dict,
    api_key: str,
    model: str = "gemini-2.0-flash-exp",
    format_style: str = "bullet",
) -> str:
    """Use Gemini to generate a professional management email."""

    if not api_key:
        raise ValueError("API key is required. Set GOOGLE_API_KEY environment variable or pass it as an argument.")

    # Initialize Gemini client with API key
    client = genai.Client(api_key=api_key)

    # Check if we have GitHub PR data
    has_prs = "github_prs" in summary_data

    # Create a detailed prompt for Gemini based on format style
    if format_style == "paragraph":
        prompt = f"""
You are a technical professional writing an executive summary for senior management.
Based on the following YouTrack issue data{" and GitHub Pull Request data" if has_prs else ""}, create a professional email in PARAGRAPH FORMAT ONLY.

KEY GUIDELINES:
1. Write in flowing paragraphs - NO bullet points, NO lists, NO ticket IDs, NO PR numbers
2. Focus on HIGH-LEVEL themes and overall impact
3. Group accomplishments into 3-4 narrative paragraphs by theme:
   - Paragraph 1: Opening summary with quantified achievements
   - Paragraph 2-3: Thematic areas (e.g., "Critical system stability improvements", "Workflow automation enhancements")
   - Paragraph 4: Closing statement about ongoing commitment
4. Use smooth transitions between sentences and paragraphs
5. Mention areas of work (animation, compositing, editorial, etc.) but avoid technical ticket references
6. Keep it executive-appropriate - emphasize business value and operational impact
7. Total length: 4-5 concise paragraphs (250-350 words)
8. Natural, flowing prose style suitable for executive leadership
"""
    else:
        prompt = f"""
You are a technical professional writing a balanced work summary email to management for audit purposes.
Based on the following YouTrack issue data{" and GitHub Pull Request data" if has_prs else ""}, create a professional email that highlights
contributions to the production pipeline over the past months.

KEY GUIDELINES:
1. Be CONCISE but SPECIFIC - avoid repetitive Problem/Solution/Impact patterns
2. Use nested bullet points with 2 levels maximum:
   - Main category/area (e.g., "Critical Production Blockers", "Pipeline Tooling")
     - Specific accomplishments with brief impact statement (1 line each)
3. Group work by themes/departments affected
4. For each item, mention:
   - What was fixed/built (1 brief sentence)
   - Impact in concrete terms (e.g., "unblocked animation team", "reduced export time 40%")
5. Integrate code contributions naturally within categories (don't separate them)
6. Highlight critical/show-stopper items with priority indicators
7. Keep descriptions factual and audit-appropriate - focus on deliverables
8. Emphasize completed, merged work that's now in production
9. Total length should be 3-4 concise paragraphs with organized bullet lists

YOUTRACK DATA SUMMARY:
- Total Issues Involved: {summary_data["total_issues"]}
- Issues Assigned & Worked On: {summary_data["assigned_issues"]}
- Issues Provided Technical Support: {summary_data["commented_issues"]}

ISSUE STATES:
{json.dumps(summary_data["states"], indent=2)}

ISSUE TYPES:
{json.dumps(summary_data["types"], indent=2)}

PRIORITY LEVELS:
{json.dumps(summary_data["priorities"], indent=2)}

TOP ISSUES WORKED ON:
{json.dumps(summary_data["issues_detail"][:15], indent=2)}
"""

    if has_prs:
        pr_data = summary_data["github_prs"]
        prompt += f"""

GITHUB PULL REQUESTS SUMMARY:
- Total PRs: {pr_data["total_prs"]}
- Authored: {pr_data["authored"]}
- Assigned: {pr_data["assigned"]}
- Merged: {pr_data["merged"]}
- Open: {pr_data["open"]}

PR STATES:
{json.dumps(pr_data["states"], indent=2)}

REPOSITORIES CONTRIBUTED TO:
{json.dumps(pr_data["repositories"], indent=2)}

KEY PULL REQUESTS:
{json.dumps(pr_data["prs_detail"][:15], indent=2)}

When mentioning code contributions, highlight:
- Lines of code added/changed
- Repositories contributed to
- Successfully merged changes
- Code review participation
"""

    if format_style == "paragraph":
        prompt += """

Generate an executive-style email with:
- Subject line emphasizing strategic production improvements
- Opening paragraph summarizing scope of contributions (with numbers but no specific ticket IDs)
- 2-3 body paragraphs, each covering a thematic area in narrative form
- Closing paragraph reaffirming commitment to pipeline excellence
- Professional signature placeholder

EXAMPLE PARAGRAPH STYLE:
"During this period, significant progress was made in stabilizing our production pipeline across multiple departments. The animation team benefited from comprehensive improvements to the playback and review tools, which eliminated audio synchronization issues and streamlined the review submission process. These enhancements resulted in faster iteration cycles and improved collaboration between animation and downstream departments.

In parallel, critical attention was directed toward data integrity and workflow automation. The integration between our asset management and production tracking systems was strengthened, providing better visibility into asset lineage and version control. Additionally, the editorial department gained enhanced timeline import capabilities, which removed previous bottlenecks in the ingestion process."

Keep it flowing and executive-appropriate. NO ticket IDs, NO PR numbers, NO bullet points.
"""
    else:
        prompt += """

Generate a professional, audit-appropriate email with:
- Subject line emphasizing production contributions
- Opening paragraph (2-3 sentences) with quantified summary
- Main body with 2-3 organized categories using nested bullets:
  * Category name
    - Achievement 1: Brief description + impact (1 line)
    - Achievement 2: Brief description + impact (1 line)
- Include code contribution statistics naturally (e.g., "delivered via 45 merged PRs across 8 repositories")
- Closing statement (1 sentence) about continued pipeline support
- Professional signature placeholder

FORMATTING EXAMPLE:
**Critical Production Blockers Resolved**
  - Fixed audio playback in Maya playblast tool (USER-568) - unblocked animation review workflows, merged PR #13 with 1172 additions
  - Resolved Comp render publishing failures on Deadline (USER-551) - restored daily render submissions for compositing team
  - Eliminated Unreal FBX import crashes (USER-564) - prevented editor crashes affecting multiple departments

Keep it factual, concise, and professional. Avoid repetitive problem/solution/impact patterns.
Focus on concrete deliverables suitable for audit review.
"""

    # Generate content using Gemini
    print(f"  Using model: {model}")
    response = client.models.generate_content(model=model, contents=prompt)

    return response.text


def save_email_draft(email_content: str, filename: str = "management_report_email.txt"):
    """Save the generated email to a file."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename_with_timestamp = f"{filename.rsplit('.', 1)[0]}_{timestamp}.{filename.rsplit('.', 1)[1]}"

    with open(filename_with_timestamp, "w", encoding="utf-8") as f:
        f.write(email_content)

    print(f"\n✅ Email draft saved to: {filename_with_timestamp}")
    return filename_with_timestamp


def select_output_format() -> str:
    """Prompt user to select output format."""
    print("\n" + "=" * 80)
    print("SELECT OUTPUT FORMAT")
    print("=" * 80)
    print("\nAvailable formats:")
    print("  1. Bullet points with ticket IDs and PR numbers (audit-style)")
    print("  2. Paragraph format without ticket IDs or PR numbers (executive-style)")

    while True:
        try:
            choice = input("\nSelect format (1-2) or press Enter for default [1]: ").strip()

            if not choice:
                return "bullet"

            choice_num = int(choice)
            if choice_num == 1:
                return "bullet"
            elif choice_num == 2:
                return "paragraph"
            else:
                print("❌ Please enter 1 or 2")
        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled by user")
            exit(0)


def select_model() -> str:
    """Prompt user to select a Gemini model."""
    print("\n" + "=" * 80)
    print("SELECT GEMINI MODEL")
    print("=" * 80)
    print("\nAvailable models:")
    for i, model in enumerate(AVAILABLE_MODELS, 1):
        print(f"  {i}. {model}")

    while True:
        try:
            choice = input(
                f"\nSelect model (1-{len(AVAILABLE_MODELS)}) or press Enter for default [{AVAILABLE_MODELS[0]}]: "
            ).strip()

            if not choice:
                return AVAILABLE_MODELS[0]

            choice_num = int(choice)
            if 1 <= choice_num <= len(AVAILABLE_MODELS):
                return AVAILABLE_MODELS[choice_num - 1]
            else:
                print(f"❌ Please enter a number between 1 and {len(AVAILABLE_MODELS)}")
        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\n❌ Cancelled by user")
            exit(0)


def main():
    """
    Generate professional management report email using Google AI.

    Prerequisites:
        - Environment configuration file (.env or ~/.gishant_scripts.env) with:
            GOOGLE_AI_API_KEY=your-api-key-here

        - my_youtrack_issues.json: Generated by running fetch_youtrack_issues.py
        - my_github_prs.json: (Optional) Generated by running fetch_github_prs.py

    Configuration:
        See .env.example for full configuration template.
        Get Google AI API key from: https://aistudio.google.com/apikey

    Returns:
        Exit code 0 on success, 1 on error.
    """
    print("=" * 80)
    print("MANAGEMENT REPORT EMAIL GENERATOR")
    print("=" * 80)

    # Check for JSON file
    json_file = "my_youtrack_issues.json"
    if not os.path.exists(json_file):
        print(f"\n❌ Error: {json_file} not found!")
        print("Please run fetch_youtrack_issues.py first to generate the data.")
        return 1

    try:
        # Load issues data
        print(f"\n📂 Loading issues from {json_file}...")
        issues = load_issues_data(json_file)
        print(f"✓ Loaded {len(issues)} issues")

        # Load GitHub PRs data
        print("\n📂 Loading GitHub PRs from my_github_prs.json...")
        prs = load_github_prs()
        if prs:
            print(f"✓ Loaded {len(prs)} pull requests")
        else:
            print("⚠️  No GitHub PR data found (optional)")

        # Prepare summary
        print("\n📊 Analyzing work contributions...")
        summary_data = prepare_summary_data(issues, prs)
        print(f"✓ Assigned to {summary_data['assigned_issues']} issues")
        print(f"✓ Provided input on {summary_data['commented_issues']} additional issues")

        if prs:
            pr_data = summary_data["github_prs"]
            print(f"✓ {pr_data['authored']} PRs authored")
            print(f"✓ {pr_data['merged']} PRs merged")

        # Select output format
        output_format = select_output_format()

        # Select model
        selected_model = select_model()

        # Generate email with Gemini
        print("\n🤖 Generating professional email with Gemini AI...")
        print("(This may take a few moments...)")

        # Get API key from configuration
        from gishant_scripts.core.config import AppConfig
        from gishant_scripts.core.errors import ConfigurationError

        try:
            config = AppConfig()
            config.require_valid("google_ai")
            api_key = config.google_ai.api_key
        except ConfigurationError:
            print("\n" + "=" * 80)
            print("⚠️  GOOGLE_AI_API_KEY not found in environment")
            print("=" * 80)
            print("\nPlease provide your Google AI API key.")
            print("You can get one from: https://aistudio.google.com/apikey")
            print("\nOption 1: Set in .env file")
            print("  GOOGLE_AI_API_KEY=your-api-key-here")
            print("\nOption 2: Set environment variable")
            print("  export GOOGLE_AI_API_KEY='your-api-key-here'")
            print("\nOption 3: Enter it now (will not be saved)")
            api_key = input("\nEnter your Google API key: ").strip()

            if not api_key:
                print("\n❌ No API key provided. Exiting.")
                return 1

        email_content = generate_email_with_gemini(summary_data, api_key, selected_model, output_format)

        # Display the generated email
        print("\n" + "=" * 80)
        print("GENERATED EMAIL DRAFT")
        print("=" * 80)
        print(email_content)
        print("=" * 80)

        # Save to file
        saved_file = save_email_draft(email_content)

        print("\n✅ SUCCESS! Email draft generated and saved.")
        print(f"📧 Review and customize: {saved_file}")
        print(f"📊 Based on {len(issues)} YouTrack issues")
        if prs:
            print(f"📊 Based on {len(prs)} GitHub pull requests")
        print(f"🤖 Generated using: {selected_model}")
        print(
            f"📝 Output format: {'Paragraph (executive-style)' if output_format == 'paragraph' else 'Bullet points (audit-style)'}"
        )

    except FileNotFoundError as e:
        print(f"\n❌ Error: File not found - {e}")
        return 1
    except Exception as e:
        print(f"\n❌ Error generating email: {e}")
        print(f"Error type: {type(e).__name__}")
        import traceback

        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
