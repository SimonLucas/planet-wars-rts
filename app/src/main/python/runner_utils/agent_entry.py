from pydantic import BaseModel
from typing import List, Optional


class AgentEntry(BaseModel):
    id: str
    repo_url: str
    port: Optional[int] = None  # ← optional port number
    commit: Optional[str] = None  # ← optional commit hash


sample_entries: List[AgentEntry] = [
    AgentEntry(
        id="agent2",
        repo_url="https://github.com/SimonLucas/planet-wars-rts",
    ),
]


if __name__ == "__main__":
    print(sample_entries)
