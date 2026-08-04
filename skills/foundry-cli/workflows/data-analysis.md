# Data Analysis Workflows

Common patterns for data exploration and analysis with foundry-cli.

## Basic Data Exploration

```bash
# 1. List ontologies to understand data structure
foundry ontology list

# 2. Explore specific ontology
foundry ontology get ri.ontology.main.ontology.abc123

# 3. See available object types
foundry ontology object-type-list ri.ontology.main.ontology.abc123

# 4. Check current user permissions
foundry admin user current

# 5. Search recent builds to understand activity
foundry orchestration builds search
```

## SQL-Based Analysis

### Exploratory Workflow

```bash
# 1. Test connectivity with simple query
foundry sql execute "SELECT 1 as test"

# 2. Explore data structure
foundry sql execute "DESCRIBE my_dataset"

# 3. Sample data
foundry sql execute "SELECT * FROM my_dataset LIMIT 10"

# 4. Run analysis and export
foundry sql execute "
  SELECT category,
         COUNT(*) as total_count,
         AVG(value) as avg_value
  FROM my_dataset
  WHERE date_column >= '2025-01-01'
  GROUP BY category
  ORDER BY total_count DESC
" --format csv --output analysis.csv
```

### Long-Running Queries

```bash
# Submit query asynchronously
QUERY_ID=$(foundry sql submit "SELECT * FROM huge_dataset WHERE complex_condition")
echo "Query ID: $QUERY_ID"

# Check status
foundry sql status $QUERY_ID

# Wait for results
foundry sql wait $QUERY_ID --format csv --output results.csv
```

### Parallel Query Execution

```bash
# Submit multiple queries
Q1=$(foundry sql submit "SELECT * FROM table1")
Q2=$(foundry sql submit "SELECT * FROM table2")
Q3=$(foundry sql submit "SELECT * FROM table3")

# Wait for all in parallel
foundry sql wait $Q1 --output results1.csv &
foundry sql wait $Q2 --output results2.csv &
foundry sql wait $Q3 --output results3.csv &
wait
```

## Ontology-Based Analysis

```bash
ONTOLOGY="ri.ontology.main.ontology.abc123"

# 1. Explore object types
foundry ontology object-type-list $ONTOLOGY

# 2. Get object type details
foundry ontology object-type-get $ONTOLOGY Employee

# 3. List objects with specific properties
foundry ontology object-list $ONTOLOGY Employee \
  --properties "name,department,startDate" \
  --format json --output employees.json

# 4. Get specific object
foundry ontology object-get $ONTOLOGY Employee "john.doe"

# 5. Find linked objects
foundry ontology object-linked $ONTOLOGY Employee "john.doe" worksOn

# 6. Aggregate data
foundry ontology object-aggregate $ONTOLOGY Employee \
  '{"count": "count", "avg_salary": "avg"}' \
  --group-by department \
  --format csv --output department_stats.csv
```

## Dataset Exploration

```bash
DATASET="ri.foundry.main.dataset.abc123"

# Get dataset info
foundry dataset get $DATASET

# List branches
foundry dataset branches list $DATASET

# List files
foundry dataset files list $DATASET

# Get schema
foundry dataset schema get $DATASET

# Preview data
foundry dataset preview $DATASET --limit 10

# Download specific file
foundry dataset files get $DATASET "/data/results.csv" "./local_results.csv"
```

## Time Series Analysis

```bash
# Daily trends (last 30 days)
foundry sql execute "
  SELECT
    DATE(timestamp) as date,
    COUNT(*) as daily_count,
    AVG(value) as daily_average
  FROM time_series_data
  WHERE timestamp >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)
  GROUP BY DATE(timestamp)
  ORDER BY date
" --format csv --output daily_trends.csv

# Weekly aggregation
foundry sql execute "
  SELECT
    YEAR(timestamp) as year,
    WEEK(timestamp) as week,
    SUM(value) as weekly_total
  FROM time_series_data
  WHERE timestamp >= DATE_SUB(CURRENT_DATE, INTERVAL 12 WEEK)
  GROUP BY YEAR(timestamp), WEEK(timestamp)
  ORDER BY year, week
" --format csv --output weekly_analysis.csv
```

## Cohort Analysis

```bash
# User registration cohorts
foundry sql execute "
  SELECT
    DATE_FORMAT(registration_date, '%Y-%m') as cohort_month,
    COUNT(*) as cohort_size
  FROM users
  GROUP BY DATE_FORMAT(registration_date, '%Y-%m')
  ORDER BY cohort_month
"

# Retention analysis
foundry sql execute "
  WITH cohorts AS (
    SELECT
      user_id,
      DATE_FORMAT(MIN(activity_date), '%Y-%m') as cohort_month
    FROM user_activity
    GROUP BY user_id
  )
  SELECT
    c.cohort_month,
    COUNT(DISTINCT c.user_id) as cohort_size,
    COUNT(DISTINCT a.user_id) as active_users
  FROM cohorts c
  LEFT JOIN user_activity a ON c.user_id = a.user_id
    AND a.activity_date >= DATE_SUB(CURRENT_DATE, INTERVAL 30 DAY)
  GROUP BY c.cohort_month
  ORDER BY c.cohort_month
" --format csv --output retention.csv
```

## Interactive Analysis

Use shell mode for exploratory work:

```bash
foundry shell start --profile production

# In shell:
foundry> admin user current
foundry> ontology list
foundry> sql execute "SELECT * FROM dataset LIMIT 5"
foundry> sql execute "SELECT category, COUNT(*) FROM dataset GROUP BY category"
foundry> exit
```

## Best Practices

1. **Start simple**: Use `LIMIT` before running full queries
2. **Use async for large data**: `submit` + `wait` prevents timeouts
3. **Export results**: Use `--output` to save for further analysis
4. **Use JSON for scripting**: `--format json` for programmatic processing
5. **Use shell for exploration**: Interactive mode with tab completion
