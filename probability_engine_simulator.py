# -*- coding: utf-8 -*-

from __future__ import annotations

import random
import statistics
from dataclasses import dataclass
from typing import Dict, List, Tuple


BET_SIZE = 1
INITIAL_BANKROLL = 50
TARGET_BANKROLL = 100
MAX_ROUNDS = 500
SIMULATION_TIMES = 20000

# Outcome table: outcome_name -> (probability, payout_multiplier)
# payout_multiplier means total payout relative to bet, not net profit.
# Example: 2.0 means player receives 2 credits when betting 1 credit.
PAY_TABLE: Dict[str, Tuple[float, float]] = {
    "lose": (0.6, 0.0),
    "small_win": (0.25, 1.5),
    "medium_win": (0.1, 2.0),
    "big_win": (0.049, 5.0),
    "jackpot": (0.001, 50.0),
}


@dataclass
class RoundResult:
    outcome: str
    payout: float
    net_profit: float
    bankroll_after: float


@dataclass
class SimulationSummary:
    total_rounds: int
    final_bankroll: float
    total_bet: float
    total_payout: float
    actual_rtp: float
    max_bankroll: float
    min_bankroll: float
    reached_target: bool
    bankrupt: bool


def validate_pay_table(pay_table: Dict[str, Tuple[float, float]]) -> None:
    probability_sum = sum(prob for prob, _ in pay_table.values())
    if abs(probability_sum - 1.0) > 1e-9:
        raise ValueError(f"Pay table probabilities must sum to 1. Current sum = {probability_sum}")


def calculate_theoretical_metrics(pay_table: Dict[str, Tuple[float, float]], bet_size: float) -> Dict[str, float]:
    """Calculate theoretical RTP, expected value, variance and house edge."""
    expected_payout = sum(prob * payout_multiplier * bet_size for prob, payout_multiplier in pay_table.values())
    expected_net_profit = expected_payout - bet_size

    net_values = [(payout_multiplier * bet_size - bet_size, prob) for prob, payout_multiplier in pay_table.values()]
    variance = sum(prob * (net - expected_net_profit) ** 2 for net, prob in net_values)
    standard_deviation = variance ** 0.5

    rtp = expected_payout / bet_size
    house_edge = 1 - rtp

    return {
        "expected_payout": expected_payout,
        "expected_net_profit": expected_net_profit,
        "rtp": rtp,
        "house_edge": house_edge,
        "variance": variance,
        "standard_deviation": standard_deviation,
    }


def draw_outcome(pay_table: Dict[str, Tuple[float, float]]) -> Tuple[str, float]:
    """Draw one outcome based on probability weights."""
    random_value = random.random()
    cumulative = 0.0

    for outcome, (probability, payout_multiplier) in pay_table.items():
        cumulative += probability
        if random_value <= cumulative:
            return outcome, payout_multiplier

    # Floating point fallback
    outcome, (_, payout_multiplier) = next(reversed(pay_table.items()))
    return outcome, payout_multiplier


def play_one_round(bankroll: float, pay_table: Dict[str, Tuple[float, float]], bet_size: float) -> RoundResult:
    if bankroll < bet_size:
        raise ValueError("Bankroll is lower than bet size.")

    outcome, payout_multiplier = draw_outcome(pay_table)
    payout = payout_multiplier * bet_size
    net_profit = payout - bet_size
    bankroll_after = bankroll + net_profit

    return RoundResult(outcome, payout, net_profit, bankroll_after)


def simulate_single_session(
    pay_table: Dict[str, Tuple[float, float]],
    initial_bankroll: float,
    target_bankroll: float,
    bet_size: float,
    max_rounds: int,
) -> SimulationSummary:
    bankroll = initial_bankroll
    total_bet = 0.0
    total_payout = 0.0
    max_bankroll = bankroll
    min_bankroll = bankroll
    rounds = 0

    while rounds < max_rounds and bankroll >= bet_size and bankroll < target_bankroll:
        result = play_one_round(bankroll, pay_table, bet_size)
        bankroll = result.bankroll_after
        total_bet += bet_size
        total_payout += result.payout
        rounds += 1
        max_bankroll = max(max_bankroll, bankroll)
        min_bankroll = min(min_bankroll, bankroll)

    actual_rtp = total_payout / total_bet if total_bet > 0 else 0.0

    return SimulationSummary(
        total_rounds=rounds,
        final_bankroll=bankroll,
        total_bet=total_bet,
        total_payout=total_payout,
        actual_rtp=actual_rtp,
        max_bankroll=max_bankroll,
        min_bankroll=min_bankroll,
        reached_target=bankroll >= target_bankroll,
        bankrupt=bankroll < bet_size,
    )


def monte_carlo_analysis(
    pay_table: Dict[str, Tuple[float, float]],
    initial_bankroll: float,
    target_bankroll: float,
    bet_size: float,
    max_rounds: int,
    simulation_times: int,
) -> Dict[str, float]:
    sessions = [
        simulate_single_session(pay_table, initial_bankroll, target_bankroll, bet_size, max_rounds)
        for _ in range(simulation_times)
    ]

    final_bankrolls = [s.final_bankroll for s in sessions]
    rounds_played = [s.total_rounds for s in sessions]
    rtp_values = [s.actual_rtp for s in sessions if s.total_bet > 0]

    target_count = sum(1 for s in sessions if s.reached_target)
    bankrupt_count = sum(1 for s in sessions if s.bankrupt)

    return {
        "simulation_times": simulation_times,
        "avg_final_bankroll": statistics.mean(final_bankrolls),
        "median_final_bankroll": statistics.median(final_bankrolls),
        "avg_rounds_played": statistics.mean(rounds_played),
        "avg_actual_rtp": statistics.mean(rtp_values),
        "target_probability": target_count / simulation_times,
        "bankruptcy_probability": bankrupt_count / simulation_times,
    }


def build_markov_transition_probabilities(
    pay_table: Dict[str, Tuple[float, float]],
    bet_size: int,
) -> Dict[int, float]:
    """Convert payout table into bankroll net-change probabilities."""
    transition_probabilities: Dict[int, float] = {}

    for probability, payout_multiplier in pay_table.values():
        net_change = int(round(payout_multiplier * bet_size - bet_size))
        transition_probabilities[net_change] = transition_probabilities.get(net_change, 0.0) + probability

    return transition_probabilities


def markov_absorption_analysis(
    pay_table: Dict[str, Tuple[float, float]],
    initial_bankroll: int,
    target_bankroll: int,
    bet_size: int,
    iterations: int = 10000,
) -> Dict[str, float]:
    """
    Estimate absorption probabilities using iterative Markov chain value updates.

    State definition:
    - 0 means ruin / bankrupt absorbing state.
    - target_bankroll means success absorbing state.
    - 1 to target_bankroll - 1 are transient bankroll states.

    This solves the probability of reaching target before ruin from each bankroll state.
    """
    transition_probabilities = build_markov_transition_probabilities(pay_table, bet_size)

    # target_probability[state] = probability of reaching target before ruin
    target_probability = [0.0] * (target_bankroll + 1)
    target_probability[target_bankroll] = 1.0

    # expected_steps[state] = expected number of rounds before absorption
    expected_steps = [0.0] * (target_bankroll + 1)

    for _ in range(iterations):
        new_target_probability = target_probability.copy()
        new_expected_steps = expected_steps.copy()

        for state in range(1, target_bankroll):
            probability_sum = 0.0
            step_sum = 1.0

            for net_change, probability in transition_probabilities.items():
                next_state = state + net_change
                next_state = max(0, min(target_bankroll, next_state))
                probability_sum += probability * target_probability[next_state]
                step_sum += probability * expected_steps[next_state]

            new_target_probability[state] = probability_sum
            new_expected_steps[state] = step_sum

        target_probability = new_target_probability
        expected_steps = new_expected_steps

    return {
        "target_probability": target_probability[initial_bankroll],
        "ruin_probability": 1 - target_probability[initial_bankroll],
        "expected_rounds_to_absorption": expected_steps[initial_bankroll],
    }


def print_pay_table(pay_table: Dict[str, Tuple[float, float]]) -> None:
    print("\n=== Pay Table ===")
    print("Outcome | Probability | Payout Multiplier")
    for outcome, (probability, payout_multiplier) in pay_table.items():
        print(f"{outcome:10s} | {probability:10.3%} | {payout_multiplier:16.2f}x")


def print_theoretical_metrics(metrics: Dict[str, float]) -> None:
    print("\n=== Theoretical Metrics ===")
    print(f"Expected payout per round : {metrics['expected_payout']:.4f}")
    print(f"Expected net profit       : {metrics['expected_net_profit']:.4f}")
    print(f"RTP                       : {metrics['rtp']:.2%}")
    print(f"House edge                : {metrics['house_edge']:.2%}")
    print(f"Variance                  : {metrics['variance']:.4f}")
    print(f"Standard deviation        : {metrics['standard_deviation']:.4f}")


def print_monte_carlo_result(result: Dict[str, float]) -> None:
    print("\n=== Monte Carlo Simulation ===")
    print(f"Simulation times          : {result['simulation_times']:.0f}")
    print(f"Average final bankroll    : {result['avg_final_bankroll']:.2f}")
    print(f"Median final bankroll     : {result['median_final_bankroll']:.2f}")
    print(f"Average rounds played     : {result['avg_rounds_played']:.2f}")
    print(f"Average actual RTP        : {result['avg_actual_rtp']:.2%}")
    print(f"Target reached probability: {result['target_probability']:.2%}")
    print(f"Bankruptcy probability    : {result['bankruptcy_probability']:.2%}")


def print_markov_result(result: Dict[str, float]) -> None:
    print("\n=== Markov Chain Absorption Analysis ===")
    print(f"Target probability        : {result['target_probability']:.2%}")
    print(f"Ruin probability          : {result['ruin_probability']:.2%}")
    print(f"Expected rounds           : {result['expected_rounds_to_absorption']:.2f}")


def main() -> None:
    validate_pay_table(PAY_TABLE)

    print("Probability Game Engine Simulator")
    print("=================================")
    print(f"Initial bankroll: {INITIAL_BANKROLL}")
    print(f"Target bankroll : {TARGET_BANKROLL}")
    print(f"Bet size        : {BET_SIZE}")
    print(f"Max rounds      : {MAX_ROUNDS}")

    print_pay_table(PAY_TABLE)

    theoretical_metrics = calculate_theoretical_metrics(PAY_TABLE, BET_SIZE)
    print_theoretical_metrics(theoretical_metrics)

    monte_carlo_result = monte_carlo_analysis(
        PAY_TABLE,
        INITIAL_BANKROLL,
        TARGET_BANKROLL,
        BET_SIZE,
        MAX_ROUNDS,
        SIMULATION_TIMES,
    )
    print_monte_carlo_result(monte_carlo_result)

    markov_result = markov_absorption_analysis(
        PAY_TABLE,
        INITIAL_BANKROLL,
        TARGET_BANKROLL,
        BET_SIZE,
    )
    print_markov_result(markov_result)


if __name__ == "__main__":
    main()
