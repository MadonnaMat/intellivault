-- The research phase finished with review required — park the drafts and wait
-- for POST /agent/runs/{id}/review.
UPDATE agent_runs
   SET status = 'awaiting_review', current_node = NULL, pending = $2::jsonb, updated_at = now()
 WHERE id = $1;
