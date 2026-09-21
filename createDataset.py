"""
Chrome Feature Rollout Experiment: 'Summarize Button'
File: experiment_simulation.py
"""

import numpy as np
import pandas as pd
from scipy import stats


class ExperimentDesign:
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
        p_bar = (p1 + p2) / 2

        num = (
            self.z_alpha * np.sqrt(2 * p_bar * (1 - p_bar))
            + self.z_beta * np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
        ) ** 2
        denom = delta**2
        return int(np.ceil(num / denom))


class ExperimentSimulator:
    @staticmethod
    def generate_data(n_per_variant: int, baseline_tsr: float = 0.60, true_lift: float = 0.012) -> pd.DataFrame:
        """
        Simulates telemetry logs for Chrome profiles.
        Control: baseline TSR, 0% button interaction.
        Treatment: baseline + true_lift, with novelty and bounce effects.
        """
        np.random.seed(42)

        # Control Group (A)
        control_users = [f"usr_c_{i:07d}" for i in range(n_per_variant)]
        control_tsr = np.random.binomial(1, baseline_tsr, n_per_variant)
        control_latency = np.random.normal(loc=120, scale=25, size=n_per_variant)
        control_df = pd.DataFrame({
            "client_id": control_users,
            "variant": "control",
            "task_success": control_tsr,
            "latency_p95_ms": control_latency,
            "button_clicks": 0,
            "accidental_bounces": 0
        })

        # Treatment Group (B)
        treatment_users = [f"usr_t_{i:07d}" for i in range(n_per_variant)]
        treatment_tsr = np.random.binomial(1, min(baseline_tsr * (1 + true_lift), 1.0), n_per_variant)
        treatment_latency = np.random.normal(loc=123, scale=26, size=n_per_variant)  # +3ms client rendering cost
        
        # Simulating feature engagement and misclicks
        button_clicks = np.random.poisson(lam=1.5, size=n_per_variant)
        accidental_bounces = np.random.binomial(button_clicks, 0.12)  # 12% misclick/instant close

        treatment_df = pd.DataFrame({
            "client_id": treatment_users,
            "variant": "treatment",
            "task_success": treatment_tsr,
            "latency_p95_ms": treatment_latency,
            "button_clicks": button_clicks,
            "accidental_bounces": accidental_bounces
        })

        return pd.concat([control_df, treatment_df], ignore_index=True)


class HypothesisEvaluator:
    @staticmethod
    def evaluate(df: pd.DataFrame, alpha: float = 0.05):
        ctrl = df[df["variant"] == "control"]
        trmt = df[df["variant"] == "treatment"]

        n_ctrl, n_trmt = len(ctrl), len(trmt)
        p_ctrl = ctrl["task_success"].mean()
        p_trmt = trmt["task_success"].mean()

        # Two-sample Z-test for proportions
        pooled_p = (ctrl["task_success"].sum() + trmt["task_success"].sum()) / (n_ctrl + n_trmt)
        se_pooled = np.sqrt(pooled_p * (1 - pooled_p) * (1 / n_ctrl + 1 / n_trmt))
        z_stat = (p_trmt - p_ctrl) / se_pooled
        p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))

        # Guardrail Check: Latency T-test
        latency_ttest = stats.ttest_ind(ctrl["latency_p95_ms"], trmt["latency_p95_ms"], equal_var=False)

        print("=" * 60)
        print("EXPERIMENT EVALUATION RESULTS")
        print("=" * 60)
        print(f"Sample Size (per arm):      {n_ctrl:,}")
        print(f"Control Task Success:       {p_ctrl:.4%}")
        print(f"Treatment Task Success:     {p_trmt:.4%}")
        print(f"Absolute Lift:              {(p_trmt - p_ctrl):+.4%}")
        print(f"Relative Lift:              {((p_trmt - p_ctrl) / p_ctrl):+.2%}")
        print(f"Z-Statistic:                {z_stat:.4f}")
        print(f"P-Value:                    {p_value:.4e}")
        print("-" * 60)
        print(f"Guardrail - Latency Delta:  {(trmt['latency_p95_ms'].mean() - ctrl['latency_p95_ms'].mean()):+.2f} ms")
        print(f"Guardrail - Latency P-Val:  {latency_ttest.pvalue:.4e}")
        print("-" * 60)

        # Decision Gate
        if p_value < alpha and (p_trmt > p_ctrl):
            if (trmt['latency_p95_ms'].mean() - ctrl['latency_p95_ms'].mean()) < 10.0:
                print("DECISION: SHIP (Statistically significant positive lift; guardrails satisfied)")
            else:
                print("DECISION: HOLD (Positive lift detected, but breached latency guardrail)")
        else:
            print("DECISION: DO NOT SHIP (Failed to achieve statistically significant improvement)")
        print("=" * 60)


if __name__ == "__main__":
    design = ExperimentDesign(alpha=0.05, power=0.80, mde_relative=0.01)
    required_n = design.calculate_sample_size(baseline_rate=0.60)
    print(f"Calculated required sample size per variant: {required_n:,}")

    # Generate synthetic telemetry and evaluate
    simulated_df = ExperimentSimulator.generate_data(n_per_variant=required_n, baseline_tsr=0.60, true_lift=0.012)
    HypothesisEvaluator.evaluate(simulated_df)