-- The drafts an approved run should commit, the research phase's partial
-- result (analysis + skipped notes), and the URLs it fetched — all parked
-- alongside each other.
SELECT pending, result, source_urls FROM agent_runs WHERE id = $1;
