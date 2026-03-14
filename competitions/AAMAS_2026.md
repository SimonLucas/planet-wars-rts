# AAMAS 2026 Specifics

This competition will run in conjunction with the
[International Conference on Autonomous Agents and Multiagent Systems 2026](https://cyprusconferences.org/aamas2026/).

---

## 🗓️ Submission Deadline

**May 18, 2026 — Anywhere on Earth**
(i.e. entries must be submitted by midnight UTC−12)

---

## Introduction

The AAMAS 2026 competition will focus on the **fully observable**
mode of the game. Future competitions may switch to the
**partially observable** variant.

Please see the main [Submission Instructions](../submit_entry.md)
for details on how to submit an entry.

> ⚠️ We strongly recommend submitting your entry well before the deadline.
> Non-functioning entries will **not** be accepted.

---

## Game Variants

Game parameters will follow the default configuration,
except for the following, which will be **uniformly randomly sampled**
from the ranges below (same as previous competitions):

- **Number of planets**: 10–30
- **Neutral ratio**: 0.25–0.35
- **Growth rate**: 0.05–0.2
- **Transporter speed**: 2.0–5.0 units/tick

**Game duration** is fixed at a maximum of **2000 ticks**.

Games will run at **20 Hz**, giving agents **50 ms per decision**.
However, this is a real-time competition: agents may take longer
(but will act on stale information), and if both respond quickly,
the game will run faster.

---

## Evaluation

The winner will be determined via a **TrueSkill league**
involving all submitted entries plus a small pool of
baseline agents (including sample bots and top entries from previous competitions).

- The league will begin shortly and be updated continuously.
- Submitted entries may be re-evaluated as new submissions arrive.
- The live leaderboard is available here: [Live Leaderboard](https://github.com/SimonLucas/planet-wars-rts-submissions/blob/main/results/spring-2026/leaderboard.md)

---

## Prize Money

**There is no prize money for the AAMAS 2026 competition.**

This is an academic competition focused on advancing research
in multi-agent AI and real-time strategy. Winners will be
recognized at the conference and in related publications.

---

## Open-Sourcing Entries

Open-sourcing your agent is **not required** for this competition.

However, we encourage participants to share their code —
for example, by linking to a public GitHub repository —
to support reproducibility and future research.

---

## Terms and Conditions

By submitting an entry, you agree to the competition
[Terms and Conditions](./competition_terms.md).
