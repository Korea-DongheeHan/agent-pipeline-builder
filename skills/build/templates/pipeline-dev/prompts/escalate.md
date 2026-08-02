# Task: escalation report (convergence-loop stop)

The same acceptance items kept failing and the convergence loop is exhausted
(rule: stop after N consecutive failures and hand the judgment to the user).

## Work
From the upstream artifacts (context below), write a report for the user's
decision:

1. The repeatedly failing items and each iteration's failure evidence.
2. The implementation side's evidence and the verdict side's (qa/review)
   evidence — **present both without deleting or taking sides**.
3. The available options (revise the spec / change the approach / manual
   intervention).

## Verdict
Report SUCCEEDED once the report is written — this node is the loop
exhaustion handler (`exhausted:` target), so after your report the runner
automatically ends the pipeline as failed and the user reviews the report.
