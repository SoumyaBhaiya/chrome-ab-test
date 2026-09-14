# ✨ Summarize Button: A Chrome Feature Experiment


> Does offering a Summarize button increase the number of users who
> successfully understand an article within three minutes, without
> materially reducing comprehension?

I chose this feature because it has a clear potential benefit: helping
people understand long articles with less effort.

However, a summary could also omit important information or mislead a
reader. Therefore, I evaluate both timely comprehension and eventual
comprehension.

Button clicks are a useful adoption metric, but they do not establish
whether the feature actually helps users.


This project includes:

- A product hypothesis and experiment protocol.
- A randomization unit.
- Guardrail metrics.
- Type I and Type II error assumptions.
- Power analysis and sample-size estimation.
- Synthetic data.
- Statistical analysis and confidence intervals.
- Repeated simulations for evaluating the decision rule.
- Sensitivity analysis and reproducible figures.

## 3. Experiment experiences

| Group | Experience |
|---|---|
| Control | Read the article using the normal interface. |
| Treatment | Read the same type of article with an optional Summarize button that opens a short summary in a side panel. |

Both groups retain access to the original article.

Both groups receive the same task instructions, questions,
rules, and time limits.

The model, summary format, and interface would remain fixed during the experiment.

### Eligible population
I assume:

- The participants who use desktop Chrome.
- Articles in English with the participants having the proficiency for the same.
- One participant per registered Chrome profile.
- A curated corpus of approximately 1,000–1,500-word factual articles.
- No previous exposure to the assigned article or experimental summary.

## 4. Randomization and analysis units

**Randomization unit: a Chrome profile ID.**

Each eligible profile is assigned once to control or treatment, with
exactly half of the fixed study cohort in each group.

I chose the profile because the interface experience should remain
consistent for that participant.

**Analysis unit: the same Chrome profile.**

Each profile contributes one first-task outcome. Multiple page views or
button clicks do not count as additional independent observations.


The simulation assumes:

- Profiles represent independent participants.
- There is no cross-group sharing of summaries.
- One person does not enroll using multiple profiles.
- Assignment does not change during the study.

These are assumptions to verify operationally in a real experiment.
