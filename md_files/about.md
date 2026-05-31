This dashboard brings together yearly employment statistics from Statistics Sweden (SCB) and AI-exposure scores from the DAIOE framework to support research into how AI may be reshaping labour market outcomes across Swedish occupations.

---

### Data Sources

| Source | Description |
|---|---|
| [Swedish Occupational Register, SCB](https://www.scb.se/en/finding-statistics/statistics-by-subject-area/labour-market/labour-force-supply/the-swedish-occupational-register-with-statistics/) | Yearly employment counts and year-over-year changes by occupation, sex, and age group |
| [DAIOE Framework](https://www.ai-econlab.com/ai-exposure-daioe) | Data-driven AI Occupational Exposure scores across multiple AI capability sub-domains |

---

### Coverage

- **Geography**: Sweden (national totals)
- **Occupation levels**: SSYK 2012, all four levels (SSYK1 major groups through SSYK4 detailed units)
- **Time range**: {YEAR_MIN} to {YEAR_MAX}, updated annually
- **Employment unit**: absolute headcount (e.g. 150,000 = 150,000 people)

---

### Key Concepts

**SSYK 2012**
The Swedish Standard Classification of Occupations (2012 edition). Organises all occupations into four hierarchical levels:

| Level | Description | Example count |
|---|---|---|
| SSYK1 | Major groups (1-digit) | 9 categories |
| SSYK2 | Minor groups (2-digit) | ~30 categories |
| SSYK3 | Unit groups (3-digit) | ~100 categories |
| SSYK4 | Detailed occupational units (4-digit) | ~400 categories |

**DAIOE: AI Exposure Scores**
Data-driven AI Occupational Exposure scores quantify how strongly the tasks within an occupation may be affected by different AI capabilities. Scores are computed across multiple sub-domains (e.g. language, vision, reasoning) and aggregated as weighted averages at the occupation level.

**Percentile Rank**
Shows where an occupation sits relative to all others on a given sub-domain. A percentile rank of 80 means the occupation scores higher than 80% of all occupations; it is a relative, not absolute, measure.

**Exposure Level**
An ordinal scale from 1 (Very Low) to 5 (Very High) summarising the weighted-average AI exposure score for a sub-domain. Used for quick comparisons; the underlying index score provides more precision.

**Employment Change**
Year-over-year or multi-year percentage change computed from absolute employment counts. Positive values indicate growth; negative values indicate decline. Changes are computed from aggregated employment counts and absolute changes, not by averaging sex- or age-group-specific percentage rates.

**Age Groups**
Employment is broken down by seven age bands: Early Career 1 (16-24), Early Career 2 (25-29), Developing (30-34), Mid-Career 1 (35-39), Mid-Career 1 (40-44), Mid-Career 2 (45-49), and Senior (50+).

---

### Caveats

- AI exposure measures potential task-level exposure to AI capabilities. It is not a prediction of employment decline, job loss, or automation outcomes.
- Year-over-year employment changes may reflect economic cycles, policy changes, survey revisions, or occupational reclassifications unrelated to AI adoption.
- Percentile ranks are relative to other occupations in the dataset. A high rank does not imply a high absolute exposure score, and rankings may shift as new occupations or years are added.
- At SSYK4, many detailed occupational units have small employment counts; year-over-year changes may be volatile.
- The 3-year and 5-year change figures compare the current year against three or five years prior. They will be null for occupations with insufficient history.

---

### About the Project

This tool is developed by the [AI-Econ Lab](https://www.ai-econlab.com) as part of ongoing research into the intersection of artificial intelligence and labour markets. For questions or collaboration enquiries, please visit [ai-econlab.com](https://www.ai-econlab.com).
