"""
Chrome Feature Rollout Experiment: 'Summarize Button'
File: experiment_simulation.py
"""

import hashlib
import numpy as np
import pandas as pd
from scipy import stats


class ExperimentDesign:
    """Calculates statistical thresholds and sample size requirements."""
    def __init__(self, alpha: float = 0.05, power: float = 0.80, mde_relative: float = 0.01):
        self.alpha = alpha
        self.power = power
        self.mde_relative = mde_relative
        self.z_alpha = stats.norm.ppf(1 - alpha / 2)
        self.z_beta = stats.norm.ppf(power)

    def calculate_sample_size(self, baseline_rate: float) -> int:
        p1 = baseline_rate
        p2 = baseline_rate * (1 + self.mde_relative)
        delta = abs(p2 - p1)
        p_bar = (p1 + p2) / 2.0

        num = (
            self.z_alpha * np.sqrt(2 * p_bar * (1 - p_bar))
            + self.z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
        ) ** 2
        denom = delta**2
        return int(np.ceil(num / denom))


class AssignmentEngine:
    """Assigns users to buckets deterministically using hashing."""
    @staticmethod
    def assign_bucket(client_id: str, salt: str = "summarize_v1") -> str:
        key = f"{client_id}_{salt}".encode("utf-8")
        hash_val = int(hashlib.md5(key).hexdigest(), 16) % 100
        
        # 5% Control, 5% Treatment, 90% Production Holdout
        if hash_val < 5:
            return "control"
        elif hash_val < 10:
            return "treatment"
        else:
            return "unassigned"


class ExperimentSimulator:
    """Generates realistic client telemetry without TTI."""
    @staticmethod
    def generate_telemetry(n_per_variant: int, baseline_tsr: float = 0.60, true_tsr_lift: float = 0.012) -> pd.DataFrame:
        np.random.seed(42)

        # 1. Control Cohort (Baseline)
        control_ids = [f"usr_c_{i:07d}" for i in range(n_per_variant)]
        control_tsr = np.random.binomial(1, baseline_tsr, n_per_variant)
        # Baseline reformulation: 35% of searches require re-querying
        control_reform = np.random.binomial(1, 0.35, n_per_variant)
        control_latency = np.random.normal(loc=120.0, scale=25.0, size=n_per_variant)
        
        control_df = pd.DataFrame({
            "client_id": control_ids,
            "variant": "control",
            "task_success": control_tsr,
            "query_reformulated": control_reform,
            "latency_p95_ms": control_latency,
            "button_clicks": 0,
            "accidental_bounces": 0
        })

        # 2. Treatment Cohort (With Button)
        treatment_ids = [f"usr_t_{i:07d}" for i in range(n_per_variant)]
        treatment_tsr = np.random.binomial(1, min(baseline_tsr * (1 + true_tsr_lift), 1.0), n_per_variant)
        # Better summaries mean fewer reformulations: drops from 35% to 33.2%
        treatment_reform = np.random.binomial(1, 0.332, n_per_variant)
        # Latency penalty: DOM element injection adds ~3ms
        treatment_latency = np.random.normal(loc=123.0, scale=26.0, size=n_per_variant)
        
        # Feature usage telemetry
        button_clicks = np.random.poisson(lam=1.8, size=n_per_variant)
        accidental_bounces = np.random.binomial(button_clicks, 0.11)  # 11% misclick rate

        treatment_df = pd.DataFrame({
            "client_id": treatment_ids,
            "variant": "treatment",
            "task_success": treatment_tsr,
            "query_reformulated": treatment_reform,
            "latency_p95_ms": treatment_latency,
            "button_clicks": button_clicks,
            "accidental_bounces": accidental_bounces
        })

        return pd.concat([control_df, treatment_df], ignore_index=True)


class HypothesisEvaluator:
    """Evaluates primary OEC, secondary quality, and guardrails against decision gates."""
    @staticmethod
    def evaluate(df: pd.DataFrame, alpha: float = 0.05):
        ctrl = df[df["variant"] == "control"]
        trmt = df[df["variant"] == "treatment"]

        n_ctrl, n_trmt = len(ctrl), len(trmt)
        p_tsr_ctrl = ctrl["task_success"].mean()
        p_tsr_trmt = trmt["task_success"].mean()

        # Primary OEC: Two-sample pooled Z-test on Task Success
        pooled_p = (ctrl["task_success"].sum() + trmt["task_success"].sum()) / (n_ctrl + n_trmt)
        se_pooled = np.sqrt(pooled_p * (1 - pooled_p) * (1 / n_ctrl + 1 / n_trmt))
        z_stat = (p_tsr_trmt - p_tsr_ctrl) / se_pooled
        p_val_tsr = 2 * (1 - stats.norm.cdf(abs(z_stat)))

        # Secondary: Query Reformulation Rate
        ref_ctrl = ctrl["query_reformulated"].mean()
        ref_trmt = trmt["query_reformulated"].mean()
        ref_delta = ref_trmt - ref_ctrl

        # Guardrail 1: Latency Welch's T-Test
        lat_ctrl = ctrl["latency_p95_ms"].mean()
        lat_trmt = trmt["latency_p95_ms"].mean()
        lat_delta = lat_trmt - lat_ctrl
        lat_pvalue = stats.ttest_ind(ctrl["latency_p95_ms"], trmt["latency_p95_ms"], equal_var=False).pvalue

        # Guardrail 2: Accidental Bounce Rate
        total_clicks = trmt["button_clicks"].sum()
        total_bounces = trmt["accidental_bounces"].sum()
        bounce_rate = (total_bounces / total_clicks) if total_clicks > 0 else 0.0

        # Print Executive Report
        print("=" * 65)
        print("CHROME OMNIBOX 'SUMMARIZE' EXPERIMENT RESULTS")
        print("=" * 65)
        print(f"Sample Size (per arm):            {n_ctrl:,}")
        print(f"Primary: Control Task Success:    {p_tsr_ctrl:.4%}")
        print(f"Primary: Treatment Task Success:  {p_tsr_trmt:.4%}")
        print(f"Primary: Absolute Lift:           {(p_tsr_trmt - p_tsr_ctrl):+.4%}")
        print(f"Primary: Relative Lift:           {((p_tsr_trmt - p_tsr_ctrl) / p_tsr_ctrl):+.2%}")
        print(f"Primary: Z-Statistic:             {z_stat:.4f}")
        print(f"Primary: P-Value:                 {p_val_tsr:.4e}")
        print("-" * 65)
        print(f"Secondary: Query Reformulation:   Control {ref_ctrl:.2%} -> Trmt {ref_trmt:.2%} ({ref_delta:+.2%})")
        print("-" * 65)
        print(f"Guardrail: Latency Delta:         {lat_delta:+.2f} ms (P-Val: {lat_pvalue:.4e})")
        print(f"Guardrail: Accidental Bounces:    {bounce_rate:.2%} (Threshold: < 15.0%)")
        print("=" * 65)

        # Decision Gate Evaluation
        tsr_pass = (p_val_tsr < alpha) and (p_tsr_trmt > p_tsr_ctrl)
        latency_pass = lat_delta < 10.0
        bounce_pass = bounce_rate < 0.15
        reform_pass = ref_delta < 0.0  # Reformulation should drop

        if tsr_pass and latency_pass and bounce_pass and reform_pass:
            print("DECISION: SHIP")
            print("Justification: Statistically significant positive lift on Task Success;")
            print("               fewer query reformulations; all guardrails satisfied.")
        elif tsr_pass and not latency_pass:
            print("DECISION: HOLD (Performance Engineering Required)")
            print("Justification: Significant value detected, but exceeded 10ms latency threshold.")
        elif tsr_pass and not bounce_pass:
            print("DECISION: HOLD (UI Redesign Required)")
            print("Justification: Significant value detected, but >15% accidental clicks indicate UI clutter.")
        else:
            print("DECISION: DO NOT SHIP")
            print("Justification: Failed to achieve statistically significant improvement.")
        print("=" * 65)


if __name__ == "__main__":
    # 1. Setup statistical parameters
    design = ExperimentDesign(alpha=0.05, power=0.80, mde_relative=0.01)
    required_n = design.calculate_sample_size(baseline_rate=0.60)
    print(f"Calculated Required Sample Size: {required_n:,} profiles per arm")

    # 2. Simulate experiment telemetry logs
    telemetry_data = ExperimentSimulator.generate_telemetry(
        n_per_variant=required_n,
        baseline_tsr=0.60,
        true_tsr_lift=0.012
    )

    # 3. Evaluate hypotheses and output decision
    HypothesisEvaluator.evaluate(telemetry_data)