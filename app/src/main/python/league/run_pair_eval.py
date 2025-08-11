# run_pair_eval.py
import re
import subprocess
from pathlib import Path
from typing import Tuple

def find_project_root(start: Path = Path(__file__).resolve()) -> Path:
    for parent in [start] + list(start.parents):
        if (parent / "gradlew").is_file():
            return parent
    raise FileNotFoundError("Could not find 'gradlew' up the tree.")

AVG_RE = re.compile(r"\bAVG=([0-9.]+)")
AVG_OTHER_RE = re.compile(r"\bAVG_OTHER=([0-9.]+)")

def extract_pair_avgs(output: str) -> Tuple[float, float]:
    a = AVG_RE.search(output)
    b = AVG_OTHER_RE.search(output)
    if not a:
        raise ValueError("AVG= not found in output")
    if not b:
        raise ValueError("AVG_OTHER= not found in output")
    return float(a.group(1)), float(b.group(1))

def run_remote_pair_evaluation(port_a: int, port_b: int, games_per_pair: int = 10, timeout_ms: int = 40) -> Tuple[str, float, float]:
    """
    Runs Kotlin runRemotePairEvaluation between two remote servers.
    Returns (full_stdout, avgA, avgB).
    """
    root = find_project_root()
    csv_args = f"{port_a},{port_b},{games_per_pair},{timeout_ms}"
    print(f"⚙️  ./gradlew runRemotePairEvaluation --args={csv_args}")
    result = subprocess.run(
        ["./gradlew", "runRemotePairEvaluation", f"--args={csv_args}"],
        cwd=root,
        text=True,
        capture_output=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"Gradle run failed:\n{result.stdout}\n{result.stderr}")
    avg_a, avg_b = extract_pair_avgs(result.stdout)
    return result.stdout, avg_a, avg_b

if __name__ == "__main__":
    # time to see how long it takes to run a pair evaluation
    import time
    start_time = time.time()
    print("Running remote pair evaluation...")
    out, a, b = run_remote_pair_evaluation(62355, 62254, games_per_pair=5, timeout_ms=40)
    print(f"\nAgentA AVG={a:.1f}  AgentB AVG={b:.1f}\n")
    print("Full output:")
    print(out)
    end_time = time.time()
    print(f"Total time: {end_time - start_time:.2f} seconds")
