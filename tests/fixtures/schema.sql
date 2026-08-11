-- Minimal StudentHub schema fixture for CI integration tests.
-- Mirrors the column names of the production schema (verified 2026-08-11)
-- with a handful of synthetic rows. NO real prod data.

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS candidate_link;
DROP TABLE IF EXISTS candidate_work_history;
DROP TABLE IF EXISTS candidate_education;
DROP TABLE IF EXISTS candidate_skill;
DROP TABLE IF EXISTS request_application;
DROP TABLE IF EXISTS request;
DROP TABLE IF EXISTS company;
DROP TABLE IF EXISTS university;
DROP TABLE IF EXISTS country;

CREATE TABLE country (
  country_id INT NOT NULL AUTO_INCREMENT,
  country_name_en VARCHAR(255) NOT NULL,
  PRIMARY KEY (country_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE university (
  university_id INT NOT NULL AUTO_INCREMENT,
  university_name_en VARCHAR(255) NOT NULL,
  university_name_ar VARCHAR(255) DEFAULT NULL,
  university_country_id INT DEFAULT NULL,
  PRIMARY KEY (university_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE company (
  company_id INT NOT NULL AUTO_INCREMENT,
  parent_company_id INT DEFAULT NULL,
  company_name VARCHAR(255) NOT NULL,
  company_common_name_en VARCHAR(255) DEFAULT NULL,
  country_id INT DEFAULT NULL,
  company_hourly_rate DECIMAL(10,2) DEFAULT NULL,
  company_approved_to_hire TINYINT(1) DEFAULT 0,
  company_status_override VARCHAR(50) DEFAULT NULL,
  PRIMARY KEY (company_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate (
  candidate_id INT NOT NULL AUTO_INCREMENT,
  candidate_name VARCHAR(255) NOT NULL,
  candidate_email VARCHAR(255) NOT NULL,
  candidate_phone VARCHAR(50) DEFAULT NULL,
  country_id INT DEFAULT NULL,
  university_id INT DEFAULT NULL,
  candidate_status SMALLINT DEFAULT 0,
  candidate_created_at DATETIME DEFAULT NULL,
  PRIMARY KEY (candidate_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate_skill (
  candidate_skill_id INT NOT NULL AUTO_INCREMENT,
  candidate_id INT NOT NULL,
  skill VARCHAR(255) NOT NULL,
  deleted TINYINT(1) DEFAULT 0,
  candidate_skill_created_at DATETIME DEFAULT NULL,
  PRIMARY KEY (candidate_skill_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate_education (
  education_uuid VARCHAR(64) NOT NULL,
  candidate_id INT NOT NULL,
  university_id INT DEFAULT NULL,
  graduation_year INT DEFAULT NULL,
  PRIMARY KEY (education_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate_work_history (
  id INT NOT NULL AUTO_INCREMENT,
  candidate_id INT NOT NULL,
  company_id INT DEFAULT NULL,
  start_date DATE DEFAULT NULL,
  end_date DATE DEFAULT NULL,
  deleted TINYINT(1) DEFAULT 0,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE candidate_link (
  cl_uuid VARCHAR(64) NOT NULL,
  candidate_id INT NOT NULL,
  title VARCHAR(255) DEFAULT NULL,
  url VARCHAR(255) DEFAULT NULL,
  created_at DATETIME DEFAULT NULL,
  PRIMARY KEY (cl_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE request (
  request_uuid VARCHAR(64) NOT NULL,
  company_id INT DEFAULT NULL,
  request_position_title VARCHAR(255) DEFAULT NULL,
  request_status VARCHAR(50) DEFAULT NULL,
  request_created_datetime DATETIME DEFAULT NULL,
  request_started_at DATETIME DEFAULT NULL,
  request_delivered_at DATETIME DEFAULT NULL,
  request_priority SMALLINT DEFAULT 0,
  request_number_of_employees INT DEFAULT 1,
  PRIMARY KEY (request_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE request_application (
  application_uuid VARCHAR(64) NOT NULL,
  request_uuid VARCHAR(64) NOT NULL,
  candidate_id INT NOT NULL,
  status SMALLINT DEFAULT 0,
  created_at DATETIME DEFAULT NULL,
  PRIMARY KEY (application_uuid)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- ---------------------------------------------------------------------------
-- Fixture data (synthetic)
-- ---------------------------------------------------------------------------

INSERT INTO country (country_id, country_name_en) VALUES
  (1, 'Kuwait'), (2, 'Egypt'), (3, 'Syria');

INSERT INTO university (university_id, university_name_en, university_name_ar, university_country_id) VALUES
  (1, 'Cairo University', 'جامعة القاهرة', 2),
  (2, 'Kuwait University', 'جامعة الكويت', 1);

INSERT INTO company (company_id, parent_company_id, company_name, company_common_name_en, country_id, company_hourly_rate, company_approved_to_hire) VALUES
  (1, NULL, 'Azadea', 'Azadea', 1, 3.50, 1),
  (2, 1, 'Zama', 'Zama', 1, 2.75, 1),
  (3, 1, 'ALDA', 'ALDA', 1, 3.00, 0);

INSERT INTO candidate (candidate_id, candidate_name, candidate_email, candidate_phone, country_id, university_id, candidate_status, candidate_created_at) VALUES
  (1, 'Ali Hassan', 'ali@example.com', '+96550000001', 1, 2, 10, '2025-01-10 10:00:00'),
  (2, 'Mona Adel', 'mona@example.com', '+201000000002', 2, 1, 0, '2025-02-15 11:00:00'),
  (3, 'Sara Yousef', 'sara@example.com', '+963900000003', 3, NULL, 0, '2025-03-20 12:00:00'),
  (4, 'Ahmed Mahmoud', 'ahmed@example.com', '+201000000004', 2, 1, 1, '2025-04-25 13:00:00');

INSERT INTO candidate_skill (candidate_skill_id, candidate_id, skill, deleted) VALUES
  (1, 1, 'Retail Sales', 0),
  (2, 1, 'Customer Service', 0),
  (3, 2, 'Cash Handling', 0),
  (4, 3, 'Retail Sales', 1);

INSERT INTO candidate_education (education_uuid, candidate_id, university_id, graduation_year) VALUES
  ('edu_1', 1, 2, 2020),
  ('edu_2', 2, 1, 2021);

INSERT INTO candidate_work_history (id, candidate_id, company_id, start_date, end_date, deleted) VALUES
  (1, 1, 2, '2022-01-01', '2023-06-30', 0),
  (2, 2, 3, '2021-05-01', NULL, 0);

INSERT INTO candidate_link (cl_uuid, candidate_id, title, url, created_at) VALUES
  ('link_1', 1, 'LinkedIn', 'https://linkedin.com/in/ali', '2025-01-11 09:00:00');

INSERT INTO request (request_uuid, company_id, request_position_title, request_status, request_created_datetime, request_started_at, request_delivered_at) VALUES
  ('request_abc', 1, 'Sales Representative', 'started', '2025-05-01 09:00:00', '2025-05-02 09:00:00', NULL),
  ('request_def', 2, 'Cashier', 'delivered', '2025-04-01 09:00:00', '2025-04-02 09:00:00', '2025-05-01 09:00:00');

INSERT INTO request_application (application_uuid, request_uuid, candidate_id, status, created_at) VALUES
  ('app_1', 'request_abc', 1, 0, '2025-05-03 09:00:00'),
  ('app_2', 'request_abc', 2, 0, '2025-05-04 09:00:00'),
  ('app_3', 'request_def', 3, 0, '2025-04-03 09:00:00');

SET FOREIGN_KEY_CHECKS = 1;
