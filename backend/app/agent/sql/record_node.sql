-- Advance the progress marker after a node finishes. $3 carries the plan JSON
-- only on the step that produced it; COALESCE keeps the stored plan otherwise.
UPDATE agent_runs
   SET current_node = $2,
       plan = COALESCE($3::jsonb, plan),
       updated_at = now()
 WHERE id = $1;
