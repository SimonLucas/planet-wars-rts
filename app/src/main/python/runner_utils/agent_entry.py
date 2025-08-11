import re
from pydantic import BaseModel
from typing import Optional

"""

// sample data:

id: TeamTitansAgentV3
repo_url: https://github.com/abuzar-rasool/planet-wars-rts/commit/45276423a4a530dcd93330867e3b53a5bd5c2471
commit: 45276423a4a530dcd93330867e3b53a5bd5c2471  # optional

id: TeamTitansAgentV3
repo_url: https://github.com/abuzar-rasool/planet-wars-rts/commit/87cd5e24f83cb0befa2ac0db7dda38c63fa9fb11
commit: 87cd5e24f83cb0befa2ac0db7dda38c63fa9fb11  # optional



"""

class AgentEntry(BaseModel):
    id: str
    repo_url: str
    port: Optional[int] = None
    commit: Optional[str] = None


class AgentCommitEntry(BaseModel):
    id: str  # sanitized id + short commit hash
    repo_url: str
    commit: str  # full hash


def sanitize_image_tag(tag: str) -> str:
    """
    Sanitize a string to be safe for Docker image/container names:
    - lowercase
    - alphanumeric and dash/underscore
    """
    return re.sub(r'[^a-z0-9\-_]', '-', tag.lower())


def to_agent_commit_entry(agent: AgentEntry) -> AgentCommitEntry:
    """
    Convert AgentEntry to AgentCommitEntry:
    - Extracts commit hash from repo_url if not given
    - Normalizes repo_url to root .git
    - Appends short commit to sanitized id
    """
    repo_url = agent.repo_url.strip().rstrip("/")

    # Normalize repo URL to base repo.git
    base_match = re.match(r"(https://github\.com/[^/]+/[^/]+)", repo_url)
    if not base_match:
        raise ValueError(f"Invalid GitHub repo_url: {agent.repo_url}")

    normalized_url = f"{base_match.group(1)}.git"

    # Determine commit hash
    if agent.commit:
        commit = agent.commit.strip()
    else:
        commit_match = re.search(r"/commit/([a-f0-9]{7,40})", agent.repo_url)
        if not commit_match:
            raise ValueError(f"No commit hash provided or extractable from repo_url: {agent.repo_url}")
        commit = commit_match.group(1)

    # Create sanitized ID with short commit hash
    short_hash = commit[:7]
    clean_id = sanitize_image_tag(agent.id)
    combined_id = f"{clean_id}-{short_hash}"

    return AgentCommitEntry(
        id=combined_id,
        repo_url=normalized_url,
        commit=commit,
    )


if __name__ == "__main__":
    # Example usage
    agent = AgentEntry(
        id="IntelligentAgent",
        repo_url="https://github.com/Enerian-LZT/planet-wars-rts/commit/a1bfe3c26112b62c54ffcc3bbe74aabacb17e89e"
    )

    agent_commit = to_agent_commit_entry(agent)
    print(agent_commit)
