-- Extend users role CHECK to include senior_reviewer and viewer
-- Aligns with Python domain model valid_roles

ALTER TABLE users DROP CONSTRAINT IF EXISTS users_role_check;
ALTER TABLE users ADD CONSTRAINT users_role_check
  CHECK (role IN ('admin', 'manager', 'annotator', 'reviewer', 'senior_reviewer', 'viewer'));
