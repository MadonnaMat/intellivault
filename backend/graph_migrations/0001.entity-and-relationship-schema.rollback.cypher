// Reverse of 0001. Dropping a constraint/index that isn't there is a no-op
// thanks to IF EXISTS.
DROP INDEX related_to_owner_visibility IF EXISTS;
DROP INDEX related_to_id IF EXISTS;
DROP INDEX entity_owner_visibility IF EXISTS;
DROP CONSTRAINT entity_id_unique IF EXISTS;
