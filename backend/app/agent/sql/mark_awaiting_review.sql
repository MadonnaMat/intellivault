-- The research phase finished with review required — park the drafts ($2) and
-- the phase's partial result ($3, analysis + skipped) and wait for
-- POST /agent/runs/{id}/review. The commit phase restores $3 so the finished
-- run keeps the analysis, exactly like the non-review path.
UPDATE agent_runs
   SET status = 'awaiting_review', current_node = NULL,
       pending = $2::jsonb, result = $3::jsonb, updated_at = now()
 WHERE id = $1;
