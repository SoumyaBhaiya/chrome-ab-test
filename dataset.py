import csv
import json
import math
import platform
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from scipy.stats import norm

ROOT = Path(__file__).resolve().parent if "__file__" in globals() else Path.cwd()
OUTPUT = ROOT / "outputs"


@dataclass(frozen=True)
class Config:
    #probabilities 
    questions: int = 5
    required_correct: int = 4
    timely_seconds: int = 180
    task_limit_seconds: int = 600

    #assumption for population characteristics and planning targets.
    baseline_timely: float = 0.60
    baseline_accuracy: float = 0.80
    mde: float = 0.03
    accuracy_margin: float = 0.02

    #.
    alpha: float = 0.05
    power: float = 0.90
    round_to: int = 500

    seed: int = 42
    replications: int = 5000

    eligible_profiles_per_day: int = 1000


def validate_config(cfg):
    if not 0 < cfg.alpha < 0.5:
        raise ValueError("alpha must be between 0 and 0.5.")
    if not 0.5 < cfg.power < 1:
        raise ValueError("power must be between 0.5 and 1.")
    if not 0 < cfg.baseline_timely < cfg.baseline_accuracy < 1:
        raise ValueError("Require 0 < timely baseline < accuracy baseline < 1.")
    if cfg.mde <= 0 or cfg.accuracy_margin <= 0:
        raise ValueError("MDE and accuracy margin must be positive.")
    if cfg.round_to < 1 or cfg.replications < 100:
        raise ValueError("Invalid rounding or replication count.")
    if not 1 <= cfg.required_correct <= cfg.questions:
        raise ValueError("Invalid passing threshold.")
    if not 0 < cfg.timely_seconds < cfg.task_limit_seconds:
        raise ValueError("Invalid task windows.")
    if cfg.eligible_profiles_per_day <= 0:
        raise ValueError("Recruitment throughput must be positive.")


def required_primary_n(p0, delta, alpha, power):
    """Equal-arm normal approximation; negligible far tail omitted."""
    p1 = p0 + delta
    if not (0 < p0 < 1 and 0 < p1 < 1 and delta > 0):
        raise ValueError("Invalid primary power-analysis inputs.")

    pooled = (p0 + p1) / 2
    sigma_null = math.sqrt(2 * pooled * (1 - pooled))
    sigma_alt = math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))

    numerator = (
        norm.ppf(1 - alpha / 2) * sigma_null
        + norm.ppf(power) * sigma_alt
    )
    return math.ceil((numerator / delta) ** 2)


def sample_plan(cfg):
    primary_n = required_primary_n(
        cfg.baseline_timely, cfg.mde, cfg.alpha, cfg.power
    )

    # Wald noninferiority planning approximation under no actual harm.
    a = cfg.baseline_accuracy
    accuracy_n = math.ceil(
        2 * a * (1 - a)
        * (
            (norm.ppf(1 - cfg.alpha) + norm.ppf(cfg.power))
            / cfg.accuracy_margin
        ) ** 2
    )

    n = math.ceil(max(primary_n, accuracy_n) / cfg.round_to) * cfg.round_to

    return {
        "primary_required_per_arm": primary_n,
        "accuracy_required_per_arm_approx": accuracy_n,
        "n_per_arm": n,
        "total_profiles": 2 * n,
        "estimated_enrollment_days": math.ceil(
            2 * n / cfg.eligible_profiles_per_day
        ),
    }


def theoretical_powers(n, cfg):
    """Large-sample marginal powers under the target scenario."""
    p0 = cfg.baseline_timely
    p1 = p0 + cfg.mde
    pooled = (p0 + p1) / 2

    sigma_null = math.sqrt(2 * pooled * (1 - pooled))
    sigma_alt = math.sqrt(p0 * (1 - p0) + p1 * (1 - p1))
    critical = norm.ppf(1 - cfg.alpha / 2) * sigma_null
    shift = cfg.mde * math.sqrt(n)

    primary = (
        norm.sf((critical - shift) / sigma_alt)
        + norm.cdf((-critical - shift) / sigma_alt)
    )

    a = cfg.baseline_accuracy
    accuracy = norm.cdf(
        cfg.accuracy_margin * math.sqrt(n)
        / math.sqrt(2 * a * (1 - a))
        - norm.ppf(1 - cfg.alpha)
    )
    return float(primary), float(accuracy)


def outcome_probabilities(timely, accuracy):
    """Timely pass, late pass, unsuccessful."""
    if not 0 < timely <= accuracy < 1:
        raise ValueError(
            "Require 0 < timely probability <= eventual probability < 1."
        )
    return np.array([timely, accuracy - timely, 1 - accuracy])


def scenario_definitions(cfg):
    p = cfg.baseline_timely
    a = cfg.baseline_accuracy

    scenarios = [
        ("no_effect", p, a),
        ("target_effect", p + cfg.mde, a),
        ("small_effect", p + cfg.mde / 3, a),
        ("primary_harm", p - cfg.mde, a),
        ("accuracy_harm", p + cfg.mde, a - 2 * cfg.accuracy_margin),
        ("accuracy_boundary", p + cfg.mde, a - cfg.accuracy_margin),
    ]

    for _, timely, accuracy in scenarios:
        outcome_probabilities(timely, accuracy)

    return scenarios


def rng_for(cfg, stage, index):
    """Separate deterministic streams for datasets, calibration, curves."""
    seed = np.random.SeedSequence([cfg.seed, stage, index])
    return np.random.default_rng(seed)


def difference_statistics(control_count, treatment_count, n, alpha):
    """Vectorized pooled z-test and unpooled Wald confidence interval."""
    control_count = np.asarray(control_count, dtype=float)
    treatment_count = np.asarray(treatment_count, dtype=float)

    for counts in (control_count, treatment_count):
        if np.any(~np.isfinite(counts)):
            raise ValueError("Counts contain missing or nonfinite values.")
        if np.any((counts < 10) | (n - counts < 10)):
            raise ValueError(
                "Normal approximation requires at least 10 successes "
                "and 10 failures in each arm."
            )

    pc = control_count / n
    pt = treatment_count / n
    effect = pt - pc

    pooled = (control_count + treatment_count) / (2 * n)
    null_se = np.sqrt(pooled * (1 - pooled) * 2 / n)
    z = effect / null_se
    p_value = 2 * norm.sf(np.abs(z))

    se = np.sqrt((pc * (1 - pc) + pt * (1 - pt)) / n)
    critical = norm.ppf(1 - alpha / 2)

    return {
        "control": pc,
        "treatment": pt,
        "effect": effect,
        "se": se,
        "p_value": p_value,
        "ci_low": effect - critical * se,
        "ci_high": effect + critical * se,
    }


def evaluate_counts(cf, tf, ca, ta, n, cfg):
    """Same analysis function is used for datasets and Monte Carlo draws.

    cf/tf: control/treatment timely-success counts.
    ca/ta: control/treatment eventual-success counts.
    """
    cf, tf, ca, ta = [
        np.asarray(x, dtype=float) for x in (cf, tf, ca, ta)
    ]

    if np.any(cf > ca) or np.any(tf > ta):
        raise ValueError("Timely success cannot exceed eventual success.")

    primary = difference_statistics(cf, tf, n, cfg.alpha)
    accuracy = difference_statistics(ca, ta, n, cfg.alpha)

    accuracy_lower = (
        accuracy["effect"]
        - norm.ppf(1 - cfg.alpha) * accuracy["se"]
    )
    accuracy_ni_p = norm.sf(
        (accuracy["effect"] + cfg.accuracy_margin) / accuracy["se"]
    )

    primary_reject = primary["p_value"] < cfg.alpha
    primary_benefit = primary_reject & (primary["effect"] > 0)
    accuracy_pass = accuracy_lower > -cfg.accuracy_margin

    return {
        "control_timely": primary["control"],
        "treatment_timely": primary["treatment"],
        "timely_lift": primary["effect"],
        "timely_relative_lift": primary["effect"] / primary["control"],
        "timely_ci_low": primary["ci_low"],
        "timely_ci_high": primary["ci_high"],
        "timely_p": primary["p_value"],
        "control_accuracy": accuracy["control"],
        "treatment_accuracy": accuracy["treatment"],
        "accuracy_lift": accuracy["effect"],
        "accuracy_lower": accuracy_lower,
        "accuracy_ni_p": accuracy_ni_p,
        "primary_reject": primary_reject,
        "primary_benefit": primary_benefit,
        "accuracy_pass": accuracy_pass,
        "advance": primary_benefit & accuracy_pass,
    }


def self_checks():
    """Check decision direction and a critical impossible-data case."""
    cfg = Config(alpha=0.05, accuracy_margin=0.02)
    n = 10000

    equal = evaluate_counts(6000, 6000, 8000, 8000, n, cfg)
    assert np.isclose(equal["timely_p"], 1.0)
    assert not bool(equal["advance"])

    beneficial = evaluate_counts(6000, 6300, 8000, 8000, n, cfg)
    assert bool(beneficial["advance"])

    primary_harm = evaluate_counts(6000, 5700, 8000, 8000, n, cfg)
    assert bool(primary_harm["primary_reject"])
    assert not bool(primary_harm["advance"])

    accuracy_harm = evaluate_counts(6000, 6300, 8000, 7600, n, cfg)
    assert bool(accuracy_harm["primary_benefit"])
    assert not bool(accuracy_harm["advance"])

    try:
        evaluate_counts(6000, 6300, 8000, 6200, n, cfg)
    except ValueError:
        pass
    else:
        raise AssertionError("Impossible nested outcomes were accepted.")


def simulate_dataset(name, pt, at, n, cfg, index):
    rng = rng_for(cfg, stage=1, index=index)

    # Complete randomization: exactly n profiles assigned to each arm.
    assignment = np.repeat([0, 1], n)
    rng.shuffle(assignment)

    categories = np.empty(2 * n, dtype=int)
    arm_probabilities = [
        outcome_probabilities(cfg.baseline_timely, cfg.baseline_accuracy),
        outcome_probabilities(pt, at),
    ]

    for arm, probabilities in enumerate(arm_probabilities):
        mask = assignment == arm
        if int(mask.sum()) != n:
            raise ValueError("Allocation does not match the fixed design.")
        categories[mask] = rng.choice(3, size=n, p=probabilities)

    timely = (categories == 0).astype(int)
    eventual = (categories != 2).astype(int)

    if np.any(timely > eventual):
        raise ValueError("Invalid joint outcome generation.")

    path = OUTPUT / "data" / f"{name}.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "profile_id", "variant", "timely_success", "eventual_success"
        ])
        for i in range(2 * n):
            writer.writerow([
                f"profile_{i + 1:06d}",
                "treatment" if assignment[i] else "control",
                int(timely[i]),
                int(eventual[i]),
            ])

    control = assignment == 0
    treatment = assignment == 1
    estimates = evaluate_counts(
        timely[control].sum(),
        timely[treatment].sum(),
        eventual[control].sum(),
        eventual[treatment].sum(),
        n,
        cfg,
    )

    # Convert NumPy scalars to ordinary Python values for CSV/JSON.
    row = {
        "scenario": name,
        "n_per_arm": n,
        "true_timely_lift": pt - cfg.baseline_timely,
        "true_accuracy_lift": at - cfg.baseline_accuracy,
    }
    row.update({
        key: np.asarray(value).item()
        for key, value in estimates.items()
    })
    row["decision"] = (
        "ADVANCE_TO_VALIDATION" if row["advance"] else "DO_NOT_ADVANCE"
    )
    return row


def wilson_interval(rate, repetitions):
    """95% interval for a Monte Carlo rate, including rates of 0 or 1."""
    z = norm.ppf(0.975)
    denominator = 1 + z * z / repetitions
    center = (rate + z * z / (2 * repetitions)) / denominator
    half_width = (
        z
        * math.sqrt(
            rate * (1 - rate) / repetitions
            + z * z / (4 * repetitions ** 2)
        )
        / denominator
    )
    return center - half_width, center + half_width


def calibrate(name, pt, at, n, cfg, stage, index):
    """Multinomial counts efficiently reproduce whole experiments."""
    rng = rng_for(cfg, stage=stage, index=index)

    control = rng.multinomial(
        n,
        outcome_probabilities(cfg.baseline_timely, cfg.baseline_accuracy),
        size=cfg.replications,
    )
    treatment = rng.multinomial(
        n,
        outcome_probabilities(pt, at),
        size=cfg.replications,
    )

    estimates = evaluate_counts(
        control[:, 0],
        treatment[:, 0],
        control[:, 0] + control[:, 1],
        treatment[:, 0] + treatment[:, 1],
        n,
        cfg,
    )

    row = {
        "scenario": name,
        "n_per_arm": n,
        "replications": cfg.replications,
    }

    for metric in (
        "primary_reject", "primary_benefit", "accuracy_pass", "advance"
    ):
        rate = float(np.mean(estimates[metric]))
        low, high = wilson_interval(rate, cfg.replications)
        row[metric + "_rate"] = rate
        row[metric + "_mc_low"] = low
        row[metric + "_mc_high"] = high

    true_lift = pt - cfg.baseline_timely
    row["primary_ci_coverage"] = float(np.mean(
        (estimates["timely_ci_low"] <= true_lift)
        & (estimates["timely_ci_high"] >= true_lift)
    ))
    return row


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def make_plots(analysis, curve, plan, cfg):
    x = np.array([r["n_per_arm"] for r in curve])
    primary = np.array([r["primary_power"] for r in curve])
    accuracy = np.array([r["accuracy_power"] for r in curve])
    joint = np.array([r["joint_power"] for r in curve])
    low = np.array([r["joint_mc_low"] for r in curve])
    high = np.array([r["joint_mc_high"] for r in curve])

    fig, ax = plt.subplots(figsize=(9, 5.5))
    ax.plot(x, primary, label="Primary test: normal approximation",
            color="#2563eb")
    ax.plot(x, accuracy, label="Accuracy gate: normal approximation",
            color="#d97706")
    ax.plot(x, joint, label="Both gates: simulation", color="#111827")
    ax.fill_between(x, low, high, color="#111827", alpha=0.12)

    ax.axhline(cfg.power, color="#94a3b8", linestyle="--",
               label=f"Per-test power target: {cfg.power:.0%}")
    ax.axhline(2 * cfg.power - 1, color="#94a3b8", linestyle=":",
               label=f"Joint lower target: {2 * cfg.power - 1:.0%}")
    ax.axvline(plan["n_per_arm"], color="#059669", linestyle="--",
               label=f"Selected n/arm: {plan['n_per_arm']:,}")

    ax.set(
        xlabel="Profiles per group",
        ylabel="Probability",
        ylim=(0, 1.02),
        title="Power under the assumed target effect and unchanged accuracy",
    )
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8, loc="lower right")
    fig.tight_layout()
    fig.savefig(OUTPUT / "power_curve.png", dpi=180)
    plt.close(fig)

    effects = np.array([r["timely_lift"] for r in analysis]) * 100
    lower = np.array([r["timely_ci_low"] for r in analysis]) * 100
    upper = np.array([r["timely_ci_high"] for r in analysis]) * 100
    positions = np.arange(len(analysis))

    fig, ax = plt.subplots(figsize=(9, 5))
    ax.errorbar(
        effects,
        positions,
        xerr=np.vstack([effects - lower, upper - effects]),
        fmt="o",
        capsize=4,
        color="#2563eb",
    )
    ax.set_yticks(positions)
    ax.set_yticklabels([
        r["scenario"].replace("_", " ") for r in analysis
    ])
    ax.invert_yaxis()
    ax.axvline(0, color="#111827", linewidth=1)
    ax.axvline(100 * cfg.mde, color="#d97706", linestyle=":",
               label="Planning MDE")
    ax.set(
        xlabel="Treatment − control, percentage points; 95% Wald CI",
        title="One independently generated synthetic dataset per scenario",
    )
    ax.grid(axis="x", alpha=0.2)
    ax.legend()
    fig.tight_layout()
    fig.savefig(OUTPUT / "effect_estimates.png", dpi=180)
    plt.close(fig)


def markdown_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    lines.extend(
        "| " + " | ".join(str(value) for value in row) + " |"
        for row in rows
    )
    return "\n".join(lines)


def make_report(analysis, calibration, plan, cfg):
    theoretical_primary, theoretical_accuracy = theoretical_powers(
        plan["n_per_arm"], cfg
    )
    target = next(r for r in calibration if r["scenario"] == "target_effect")

    sections = [
        "**Synthetic results only; no real Chrome users were studied.**",
        (
            f"Seed: `{cfg.seed}`. Profiles per group: "
            f"**{plan['n_per_arm']:,}**. Monte Carlo replications per "
            f"scenario: **{cfg.replications:,}**."
        ),
        markdown_table(
            ["Planning quantity", "Value"],
            [
                ["Primary sample requirement",
                 f"{plan['primary_required_per_arm']:,} per group"],
                ["Approximate accuracy sample requirement",
                 f"{plan['accuracy_required_per_arm_approx']:,} per group"],
                ["Selected total sample", f"{plan['total_profiles']:,}"],
                ["Approximate primary power at selected sample",
                 f"{theoretical_primary:.1%}"],
                ["Approximate accuracy-gate power at selected sample",
                 f"{theoretical_accuracy:.1%}"],
            ],
        ),
        "**Estimates from one generated dataset per scenario**",
        markdown_table(
            ["Scenario", "Control timely", "Treatment timely",
             "Lift, pp", "95% CI, pp", "Primary p"],
            [
                [
                    r["scenario"],
                    f"{r['control_timely']:.2%}",
                    f"{r['treatment_timely']:.2%}",
                    f"{100 * r['timely_lift']:+.2f}",
                    (
                        f"[{100 * r['timely_ci_low']:+.2f}, "
                        f"{100 * r['timely_ci_high']:+.2f}]"
                    ),
                    f"{r['timely_p']:.4g}",
                ]
                for r in analysis
            ],
        ),
        "**Accuracy and the complete decision**",
        markdown_table(
            ["Scenario", "Accuracy change, pp",
             "One-sided lower bound, pp", "Accuracy gate", "Decision"],
            [
                [
                    r["scenario"],
                    f"{100 * r['accuracy_lift']:+.2f}",
                    f"{100 * r['accuracy_lower']:+.2f}",
                    "Pass" if r["accuracy_pass"] else "Not established",
                    (
                        "Advance to real validation"
                        if r["advance"] else "Do not advance"
                    ),
                ]
                for r in analysis
            ],
        ),
        "**Repeated-experiment validation**",
        markdown_table(
            ["Scenario", "Reject primary H0", "Significant benefit",
             "Pass accuracy", "Pass both", "Primary CI coverage"],
            [
                [
                    r["scenario"],
                    f"{r['primary_reject_rate']:.2%}",
                    f"{r['primary_benefit_rate']:.2%}",
                    f"{r['accuracy_pass_rate']:.2%}",
                    f"{r['advance_rate']:.2%}",
                    f"{r['primary_ci_coverage']:.2%}",
                ]
                for r in calibration
            ],
        ),
        (
            "For the target scenario, the estimated probability of "
            f"passing both gates is **{target['advance_rate']:.2%}**, "
            "with a 95% Monte Carlo Wilson interval of "
            f"**[{target['advance_mc_low']:.2%}, "
            f"{target['advance_mc_high']:.2%}]**."
        ),
        (
            "Primary rejection includes significant effects in either "
            "direction. A negative effect never qualifies as a benefit. "
            "At the accuracy boundary, an accuracy-gate pass is a false "
            "noninferiority declaration. Finite simulations fluctuate "
            "around their theoretical probabilities."
        ),
        (
            "These findings assess the design under assumed probabilities. "
            "They do not estimate the actual effect of a Chrome feature."
        ),
        "![Power and joint decision probability](outputs/power_curve.png)",
        "![Synthetic effect estimates](outputs/effect_estimates.png)",
    ]
    return "\n\n".join(sections)


def update_readme(report):
    path = ROOT / "README.md"
    start = "<!-- RESULTS_START -->"
    end = "<!-- RESULTS_END -->"

    if not path.exists():
        print("README.md not found; report remains in outputs/results.md.")
        return

    text = path.read_text(encoding="utf-8")
    if text.count(start) != 1 or text.count(end) != 1:
        print("README result markers missing or ambiguous; README unchanged.")
        return

    start_position = text.index(start) + len(start)
    end_position = text.index(end)

    if end_position < start_position:
        raise ValueError("README result markers are in the wrong order.")

    updated = (
        text[:start_position]
        + "\n\n"
        + report
        + "\n\n"
        + text[end_position:]
    )
    path.write_text(updated, encoding="utf-8")


def main():
    cfg = Config()
    validate_config(cfg)
    self_checks()

    plan = sample_plan(cfg)
    n = plan["n_per_arm"]
    scenarios = scenario_definitions(cfg)

    (OUTPUT / "data").mkdir(parents=True, exist_ok=True)

    analysis = []
    calibration = []

    for index, (name, pt, at) in enumerate(scenarios):
        analysis.append(
            simulate_dataset(name, pt, at, n, cfg, index)
        )
        calibration.append(
            calibrate(name, pt, at, n, cfg, stage=2, index=index)
        )

    write_csv(OUTPUT / "analysis.csv", analysis)
    write_csv(OUTPUT / "monte_carlo.csv", calibration)

    # Primary-only planning sensitivity. All combinations remain below
    # the default eventual-success probability.
    sensitivity = []
    for baseline in (0.40, 0.50, 0.60, 0.70):
        for mde in (0.01, 0.02, 0.03, 0.05):
            required = required_primary_n(
                baseline, mde, cfg.alpha, cfg.power
            )
            sensitivity.append({
                "control_timely_rate": baseline,
                "mde_absolute": mde,
                "alpha": cfg.alpha,
                "target_power": cfg.power,
                "primary_n_per_arm": required,
                "primary_n_total": 2 * required,
            })
    write_csv(OUTPUT / "sample_size_sensitivity.csv", sensitivity)

    curve = []
    maximum_n = math.ceil(1.5 * n / cfg.round_to) * cfg.round_to

    for index, curve_n in enumerate(
        range(cfg.round_to, maximum_n + 1, cfg.round_to)
    ):
        p_power, a_power = theoretical_powers(curve_n, cfg)
        joint = calibrate(
            "target_effect",
            cfg.baseline_timely + cfg.mde,
            cfg.baseline_accuracy,
            curve_n,
            cfg,
            stage=3,
            index=index,
        )
        curve.append({
            "n_per_arm": curve_n,
            "primary_power": p_power,
            "accuracy_power": a_power,
            "joint_power": joint["advance_rate"],
            "joint_mc_low": joint["advance_mc_low"],
            "joint_mc_high": joint["advance_mc_high"],
        })

    write_csv(OUTPUT / "power_curve.csv", curve)
    make_plots(analysis, curve, plan, cfg)

    manifest = {
        "data_status": "synthetic",
        "config": asdict(cfg),
        "sample_plan": plan,
        "python": platform.python_version(),
        "packages": {
            package: version(package)
            for package in ("numpy", "scipy", "matplotlib")
        },
        "scenarios": [
            {
                "name": name,
                "treatment_timely_probability": pt,
                "treatment_eventual_probability": at,
            }
            for name, pt, at in scenarios
        ],
    }
    (OUTPUT / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, allow_nan=False),
        encoding="utf-8",
    )

    report = make_report(analysis, calibration, plan, cfg)

    # Relative figure paths differ inside outputs/results.md.
    standalone_report = report.replace("(outputs/", "(")
    (OUTPUT / "results.md").write_text(
        "# Synthetic experiment results\n\n" + standalone_report + "\n",
        encoding="utf-8",
    )
    update_readme(report)

    print("Validation checks passed.")
    print(f"Primary requirement: {plan['primary_required_per_arm']:,}/arm")
    print(
        "Approximate accuracy requirement: "
        f"{plan['accuracy_required_per_arm_approx']:,}/arm"
    )
    print(f"Selected sample: {n:,}/arm; {2 * n:,} total")
    print(f"Outputs: {OUTPUT}")
    print("Synthetic results generated; no real feature effect established.")


if __name__ == "__main__":
    main()