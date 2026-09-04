-- The worker looks a run up by id alone (it already trusts the queued job) and
-- needs the owner_id to scope every graph write it makes on the caller's behalf.
SELECT id, user_id, topic, status
  FROM agent_runs
 WHERE id = $1;
