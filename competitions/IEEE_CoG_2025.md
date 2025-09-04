# IEEE CoG 2025 Specifics

This competition will run in conjunction with the  
[IEEE Conference on Games 2025](https://cog2025.inesc-id.pt/).

---

## 🗓️ Submission Deadline

**August 27, 2025 — Anywhere on Earth**  
(i.e. entries must be submitted by midnight UTC−12)

---

## Introduction

The CoG 2025 competition will focus on the **fully observable**  
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
from the ranges below (same as GECCO 2025):

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

The plan was to determine the winner via a **TrueSkill league**  
involving all submitted entries plus a small pool of  
baseline agents (including sample bots and top entries from GECCO 2025).

- The league will begin shortly and be updated continuously.
- Submitted entries may be re-evaluated as new submissions arrive.
- Once live, the league will be linked here: [TrueSkill League](https://github.com/SimonLucas/planet-wars-rts-submissions/blob/main/results/ieee-cog-2025/leaderboard.md)


### Update
While running the TrueSkill league, the results were 
found to be unstable and often not reflective of head-to-head
performance or average win rate.  

Final rankings were based on average win rates
and confirmed by checking the head-to-head win rates.
See [Results](./IEEE_CoG_2025_Results.md)

---

## Open-Sourcing Entries

Open-sourcing your agent is **not required** for this competition.

However, we encourage participants to share their code —  
for example, by linking to a public GitHub repository —  
to support reproducibility and future research.

