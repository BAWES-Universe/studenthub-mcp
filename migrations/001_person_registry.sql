-- 001_person_registry.sql — Layer 2 identity registry (additive, reversible)
--
-- PURPOSE
--   One person row per human, acting as a phone-book across all platforms:
--     discord_id   → Discord anchor (set by Discord OAuth, task 2)
--     player_ids   → one-to-many Universe player accounts (a person may
--                    have several universe accounts)
--     identities   → legacy StudentHub account links (candidate/staff/
--                    company/admin/inspector) as (account_type, legacy_id)
--
-- SAFETY
--   - ADDITIVE: creates 3 NEW tables only. Touches NO existing table,
--     no column added to legacy tables, no data moved, no ETL.
--   - REVERSIBLE: dropping the 3 tables below fully reverts Layer 2.
--   - This file is applied to prod MANUALLY after approval. The MCP server
--     is SELECT-only and never executes DDL.
--
-- APPLY (after human approval):
--   mysql -h <host> -P <port> -u <user> -p <db> < migrations/001_person_registry.sql
--
-- REVERT:
--   DROP TABLE person_identity;
--   DROP TABLE person_player;
--   DROP TABLE person;
--
-- DESIGN NOTES
--   - No FK constraints by design: this is a phone-book registry, not a
--     relational spine. Keeps DROP order free (any order) and avoids FK
--     coupling to legacy tables that may be rebuilt later.
--   - discord_id is UNIQUE (one Discord account → one person row).
--   - email/phone are NON-unique indexed: legacy data has duplicates
--     (e.g. shared emails), and a person may legitimately use several.
--   - player_id is the PRIMARY KEY of person_player (a player account
--     belongs to exactly one person).

CREATE TABLE person (
  person_id   INT NOT NULL AUTO_INCREMENT,
  display_name VARCHAR(255) DEFAULT NULL,
  email       VARCHAR(255) DEFAULT NULL,
  phone       VARCHAR(50)  DEFAULT NULL,
  discord_id  VARCHAR(64)  DEFAULT NULL,
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (person_id),
  UNIQUE KEY uq_person_discord_id (discord_id),
  KEY idx_person_email (email),
  KEY idx_person_phone (phone)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE person_player (
  person_id  INT NOT NULL,
  player_id  VARCHAR(64) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (player_id),
  KEY idx_person_player_person (person_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE person_identity (
  person_id   INT NOT NULL,
  account_type VARCHAR(32) NOT NULL,   -- candidate | staff | company | admin | inspector
  legacy_id   VARCHAR(64) NOT NULL,    -- legacy PK as string (INT or UUID)
  created_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (person_id, account_type, legacy_id),
  KEY idx_person_identity_legacy (account_type, legacy_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
