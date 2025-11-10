import json
from collections import defaultdict
from datetime import datetime


class WorkSummaryEmailGenerator:
    """Generate a professional management email from YouTrack issue data."""

    def __init__(self, json_file: str):
        """
        Initialize the email generator.

        Args:
            json_file: Path to the JSON file containing issue data
        """
        with open(json_file, encoding="utf-8") as f:
            self.issues = json.load(f)

    def categorize_issues(self) -> dict[str, list[dict]]:
        """Categorize issues by type/area based on summary and ID prefix."""
        categories = defaultdict(list)

        for issue in self.issues:
            issue_id = issue["id"]
            summary = issue["summary"]

            # Categorize based on patterns
            if "Testing" in summary or "Add-on Testing" in summary:
                categories["Testing & QA"].append(issue)
            elif "UE" in summary or "Unreal" in summary or "unreal" in summary.lower():
                categories["Unreal Engine Integration"].append(issue)
            elif "Nuke" in summary or "nuke" in summary.lower():
                categories["Nuke Integration"].append(issue)
            elif "Houdini" in summary or "houdini" in summary.lower():
                categories["Houdini Integration"].append(issue)
            elif "Maya" in summary or "maya" in summary.lower():
                categories["Maya Tools & Workflows"].append(issue)
            elif "Layout" in summary or "layout" in summary.lower():
                categories["Layout & Animation"].append(issue)
            elif "Model" in summary or "model" in summary.lower() or "Rig" in summary or "rig" in summary.lower():
                categories["Modeling & Rigging"].append(issue)
            elif "Publish" in summary or "publish" in summary.lower() or "Validator" in summary:
                categories["Publishing & Validation"].append(issue)
            elif "Kitsu" in summary or "kitsu" in summary.lower():
                categories["Kitsu Integration"].append(issue)
            elif "EDL" in summary or "Audio" in summary or "Playblast" in summary:
                categories["Editorial & Review Tools"].append(issue)
            elif issue_id.startswith("PIPE-"):
                categories["Pipeline Infrastructure"].append(issue)
            else:
                categories["General Support & Bug Fixes"].append(issue)

        return dict(categories)

    def get_time_period(self) -> str:
        """Determine the time period covered by the issues."""
        if not self.issues:
            return "recent months"

        dates = []
        for issue in self.issues:
            created = issue.get("created", "")
            if created and created != "N/A":
                try:
                    date_obj = datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
                    dates.append(date_obj)
                except ValueError:
                    pass

        if dates:
            earliest = min(dates)
            latest = max(dates)
            return f"{earliest.strftime('%B %Y')} to {latest.strftime('%B %Y')}"
        return "recent months"

    def generate_category_summary(self, category: str, issues: list[dict]) -> str:
        """Generate a summary for a category of issues."""
        summary_lines = [f"\n**{category}** ({len(issues)} issues)"]

        # Get key accomplishments
        key_items = []
        for issue in issues[:5]:  # Limit to top 5 per category
            # Clean up summary - remove technical prefixes
            clean_summary = issue["summary"]
            for prefix in ["Ayon-", "Ayon ", "Maya Ayon -", "Ayon Maya -", "USER-", "PIPE-"]:
                clean_summary = clean_summary.replace(prefix, "").strip()

            key_items.append(f"  • {clean_summary} ([{issue['id']}])")

        summary_lines.extend(key_items)

        if len(issues) > 5:
            summary_lines.append(f"  • ...and {len(issues) - 5} additional items")

        return "\n".join(summary_lines)

    def generate_email(self) -> str:
        """Generate the complete management email."""
        total_issues = len(self.issues)
        time_period = self.get_time_period()
        categories = self.categorize_issues()

        # Count assigned vs contributed
        assigned_count = sum(1 for issue in self.issues if issue.get("assignee") == "Gishant Singh")
        contributed_count = total_issues - assigned_count

        email_parts = []

        # Email header
        email_parts.append("Subject: Work Summary - Pipeline Development Contributions")
        email_parts.append("\nDear Team,\n")

        # Opening paragraph
        email_parts.append(
            f"I wanted to provide you with a summary of my contributions to the production pipeline "
            f"over the past period ({time_period}). During this time, I've been actively involved in "
            f"{total_issues} pipeline-related tasks, which include both direct assignments and collaborative "
            f"support across various departments.\n"
        )

        # Overview statistics
        email_parts.append("**Overview:**")
        email_parts.append(f"- Total Issues Involved: {total_issues}")
        email_parts.append(f"- Directly Assigned: {assigned_count}")
        email_parts.append(f"- Collaborative Support: {contributed_count}")
        email_parts.append(f"- Areas Covered: {len(categories)} major categories\n")

        # Key contributions by category
        email_parts.append("**Key Contributions by Area:**\n")

        # Sort categories by number of issues (most to least)
        sorted_categories = sorted(categories.items(), key=lambda x: len(x[1]), reverse=True)

        for category, issues in sorted_categories:
            email_parts.append(self.generate_category_summary(category, issues))

        # Impact statement
        email_parts.append("\n**Impact & Benefits:**")
        email_parts.append(
            "These efforts have contributed to:\n"
            "- Improved workflow efficiency across Maya, Unreal, Nuke, and Houdini\n"
            "- Enhanced data validation and quality control in publishing pipelines\n"
            "- Better integration between AYON and Kitsu for production tracking\n"
            "- Streamlined editorial and review processes\n"
            "- Reduced technical blockers for artists and production teams\n"
        )

        # Closing
        email_parts.append(
            "I remain committed to supporting production needs and continuously improving our pipeline "
            "infrastructure. Please let me know if you would like more detailed information about any "
            "specific area or contribution.\n"
        )

        email_parts.append("Best regards,")
        email_parts.append("Gishant Singh")
        email_parts.append("Pipeline Developer")

        # Add reference footer
        email_parts.append(
            f"\n---\n"
            f"*This summary is based on {total_issues} tracked issues from {time_period}. "
            f"For detailed technical information, please refer to the YouTrack issue tracker.*"
        )

        return "\n".join(email_parts)

    def save_email(self, filename: str = "management_work_summary.txt"):
        """Save the generated email to a file."""
        email_content = self.generate_email()

        with open(filename, "w", encoding="utf-8") as f:
            f.write(email_content)

        print(f"✅ Email draft saved to: {filename}")
        return email_content


def main():
    """Main function to generate the email."""
    json_file = "/home/gisi/dev/workspaces/rdo-dev-workspace/my_youtrack_issues.json"

    print("Generating management work summary email...")
    print(f"Reading data from: {json_file}\n")

    try:
        generator = WorkSummaryEmailGenerator(json_file)
        email_content = generator.save_email()

        print("\n" + "=" * 80)
        print("EMAIL PREVIEW")
        print("=" * 80)
        print(email_content)
        print("=" * 80)

    except FileNotFoundError:
        print(f"❌ Error: Could not find {json_file}")
        print("Please run fetch_youtrack_issues.py first to generate the data file.")
    except Exception as e:
        print(f"❌ Error generating email: {e}")


if __name__ == "__main__":
    main()
