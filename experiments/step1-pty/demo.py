"""Demo: our Python code holds a live, multi-turn conversation with interactive claude.

The two turns prove it is a REAL persistent session (turn 2 remembers turn 1) —
not a one-shot. This is the seed for wrapping an application layer around the
session later.
"""

from __future__ import annotations

from claude_session import ClaudeSession


def main() -> None:
    with ClaudeSession() as claude:
        print(">>> [our code] turn 1: stating a fact")
        reply1 = claude.send("My favorite fruit is banana. Just acknowledge in one short sentence.")
        print(f"<<< [claude] {reply1}\n")

        print(">>> [our code] turn 2: testing memory (proves a persistent session)")
        reply2 = claude.send("What is my favorite fruit? Answer with just the fruit name.")
        print(f"<<< [claude] {reply2}\n")

        ok = "banana" in reply2.lower()
        print("=" * 60)
        print(f"RESULT: persistent session memory = {'YES ✅' if ok else 'unclear'}")
        print("Our Python code communicated with the interactive claude session (no -p).")


if __name__ == "__main__":
    main()
