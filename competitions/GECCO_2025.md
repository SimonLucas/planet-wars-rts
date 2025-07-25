# GECCO 2025 Specifics

Run as a competition in conjunction with - [GECCO 2025](https://gecco-2025.sigevo.org/Competition?itemId=5108)

## This Compeitition is now closed: see the [GECCO 2025 Results](GECCO_2025_Results.md) page.

## Submission Deadline

#### July 9, 2025, Anywhere on Earth (i.e. midnight UTC-12)

We strongly recommend submitting your entry well before the deadline; non-functioning
entries will not be accepted.

## Introduction

For the GECCO 2025 competition, we will
run both full and partial observability modes.
You may enter either or both variants.

See the main [Submission Instructions](../submit_entry.md)
for details on how to submit an entry.

This page only covers the specifics for GECCO 2025.

## Game Variants

Game parameters will be as per the provided
defaults, except the following which will be
uniformly randomly sampled from the following ranges:

* Number of Planets: 10-30
* Neutral Ratio: 0.25-0.35
* Growth Rate: 0.05-0.2
* Transporter Speed: 2.0-5.0 units/tick

Game Duration will be fixed at a maximum of 2000 ticks.
Games will run at 20hz, giving up 50ms per decision
for agent to respond to the game state, but it runs
in real-time, so the agents can take longer if they wish,
albeit making decisions with stale information  (actually if
both agents respond more rapidly game will run faster).

We will also run leagues using the exact same parameters used for the 
sample leagues.

The submitted bots will be evaluated against a set
of provided agents as well as each other.

## Evaluation

For this competition there are no prizes, 
but we will rank the agents
based on their average win rates, the winner being the
agent with the highest average win rate across all games played.

We aim to run enough games to ensure a statistically significant
result, but this will depend on the number of entries and the 
true underlying difference between the best agents.

Results will be published in this repo after the competition workshop
at GECCO 2025.

## Open sourced entries?

For this competition, we will not require entries to be open sourced.
However, we encourage teams to share their code if they are willing to do so
via a public GitHub repository.
