PRAGMA foreign_keys = ON;

CREATE TABLE university (
  slug TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  short_name TEXT NOT NULL,
  map_title TEXT NOT NULL,
  primary_color TEXT NOT NULL,
  secondary_color TEXT NOT NULL,
  accent_color TEXT NOT NULL,
  catalog_url TEXT,
  catalog_date TEXT NOT NULL,
  schema_version INTEGER NOT NULL,
  academic_calendar_system TEXT NOT NULL
);

CREATE TABLE departments (
  code TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  school TEXT,
  source_url TEXT
);

CREATE TABLE courses (
  code TEXT PRIMARY KEY,
  department TEXT NOT NULL REFERENCES departments(code),
  number TEXT NOT NULL,
  level TEXT NOT NULL,
  title TEXT NOT NULL,
  credits TEXT NOT NULL,
  description TEXT,
  prerequisites TEXT,
  corequisites TEXT,
  restrictions TEXT,
  repeatable TEXT,
  source_url TEXT,
  source_catalog TEXT
);

CREATE TABLE tags (
  id INTEGER PRIMARY KEY,
  name TEXT UNIQUE NOT NULL
);

CREATE TABLE course_tags (
  course_code TEXT NOT NULL REFERENCES courses(code),
  tag_id INTEGER NOT NULL REFERENCES tags(id),
  PRIMARY KEY (course_code, tag_id)
);

CREATE TABLE prerequisite_edges (
  source_code TEXT NOT NULL,
  target_code TEXT NOT NULL REFERENCES courses(code),
  kind TEXT NOT NULL,
  source_in_database INTEGER NOT NULL,
  logic_group TEXT,
  logic_operator TEXT,
  PRIMARY KEY (source_code, target_code, kind)
);

CREATE TABLE academic_calendars (
  id TEXT PRIMARY KEY,
  university_slug TEXT NOT NULL REFERENCES university(slug),
  name TEXT NOT NULL,
  system_type TEXT NOT NULL,
  is_primary INTEGER NOT NULL,
  source_url TEXT
);

CREATE TABLE academic_terms (
  id INTEGER PRIMARY KEY,
  calendar_id TEXT NOT NULL REFERENCES academic_calendars(id),
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  academic_year TEXT NOT NULL,
  term_type TEXT NOT NULL,
  sequence INTEGER NOT NULL,
  start_date TEXT,
  end_date TEXT,
  dates_status TEXT NOT NULL CHECK (dates_status IN ('official', 'unpublished')),
  status TEXT NOT NULL,
  planning_enabled INTEGER NOT NULL,
  CHECK (
    (dates_status = 'official' AND start_date IS NOT NULL AND end_date IS NOT NULL)
    OR (dates_status = 'unpublished' AND start_date IS NULL AND end_date IS NULL)
  )
);

CREATE TABLE course_offerings (
  course_code TEXT NOT NULL REFERENCES courses(code),
  term_id INTEGER NOT NULL REFERENCES academic_terms(id),
  offering_status TEXT NOT NULL,
  source_url TEXT,
  PRIMARY KEY (course_code, term_id)
);
