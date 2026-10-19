-- =========================================================================
-- ActionMic_AI Database Schema
-- Extends the existing voice_emr database with meeting intelligence tables.
-- Run AFTER mysql_setup.sql — existing tables are NOT modified here.
-- =========================================================================

CREATE DATABASE IF NOT EXISTS actionmic_ai;
USE actionmic_ai;
-- -----------------------------------------
-- TABLE: users
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    email           VARCHAR(255) UNIQUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Insert a default system user for backward compat
INSERT IGNORE INTO users (id, name, email) VALUES (1, 'System', 'system@actionmic.local');

-- -----------------------------------------
-- TABLE: meetings
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS meetings (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    user_id             INT DEFAULT 1,
    title               VARCHAR(500) DEFAULT 'Untitled Meeting',
    description         TEXT,
    meeting_date        DATETIME,
    timezone            VARCHAR(64) DEFAULT 'Asia/Kolkata',
    duration_seconds    DECIMAL(12,2),
    status              ENUM('draft','active','completed','archived','deleted')
                            DEFAULT 'draft',
    source_type         ENUM('live','upload','imported') DEFAULT 'live',
    platform            VARCHAR(64) DEFAULT 'google_meet',
    source_language     VARCHAR(16) DEFAULT 'auto',
    target_language     VARCHAR(16) DEFAULT 'en',
    recording_status    ENUM('idle','recording','paused','stopped','failed')
                            DEFAULT 'idle',
    processing_status   ENUM('pending','processing','partial','completed','failed')
                            DEFAULT 'pending',
    audio_storage_key   VARCHAR(512),
    audio_mime_type     VARCHAR(64),
    audio_size_bytes    BIGINT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    started_at          DATETIME,
    ended_at            DATETIME,

    INDEX idx_meetings_user     (user_id),
    INDEX idx_meetings_status   (status),
    INDEX idx_meetings_date     (meeting_date),
    INDEX idx_meetings_proc     (processing_status),

    CONSTRAINT fk_meetings_user
        FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: audio_assets
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS audio_assets (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id          INT NOT NULL,
    asset_type          ENUM('original','chunk','derived','normalized')
                            DEFAULT 'original',
    storage_backend     VARCHAR(32) DEFAULT 'local',
    storage_key         VARCHAR(512) NOT NULL,
    original_filename   VARCHAR(255),
    mime_type           VARCHAR(64),
    size_bytes          BIGINT,
    duration_seconds    DECIMAL(12,2),
    checksum            VARCHAR(128),
    chunk_index         INT,
    start_offset_ms     BIGINT,
    end_offset_ms       BIGINT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_audio_assets_meeting  (meeting_id),
    INDEX idx_audio_assets_chunk    (meeting_id, chunk_index),

    CONSTRAINT fk_audio_assets_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: speakers
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS speakers (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id      INT NOT NULL,
    speaker_label   VARCHAR(64) NOT NULL,
    display_name    VARCHAR(255),
    first_seen_ms   BIGINT,
    last_seen_ms    BIGINT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_speaker_meeting_label (meeting_id, speaker_label),
    INDEX idx_speakers_meeting (meeting_id),

    CONSTRAINT fk_speakers_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: transcript_segments
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS transcript_segments (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id          INT NOT NULL,
    speaker_id          INT,
    speaker_label       VARCHAR(64),
    start_time_ms       BIGINT NOT NULL,
    end_time_ms         BIGINT NOT NULL,
    original_text       TEXT NOT NULL,
    normalized_text     TEXT,
    language_code       VARCHAR(16),
    confidence_score    DECIMAL(5,4),
    is_final            BOOLEAN DEFAULT TRUE,
    segment_index       INT,
    processing_version  INT DEFAULT 1,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_tseg_meeting      (meeting_id),
    INDEX idx_tseg_meeting_idx  (meeting_id, segment_index),
    INDEX idx_tseg_time         (meeting_id, start_time_ms),
    INDEX idx_tseg_speaker      (meeting_id, speaker_id),

    CONSTRAINT fk_tseg_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_tseg_speaker
        FOREIGN KEY (speaker_id) REFERENCES speakers(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: transcript_variants
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS transcript_variants (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    transcript_segment_id   INT NOT NULL,
    variant_type            ENUM('translation','transliteration','normalized')
                                NOT NULL,
    source_language         VARCHAR(16),
    target_language         VARCHAR(16),
    text                    TEXT NOT NULL,
    model_name              VARCHAR(128),
    confidence_score        DECIMAL(5,4),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_variant (transcript_segment_id, variant_type, target_language),
    INDEX idx_tvar_segment (transcript_segment_id),

    CONSTRAINT fk_tvar_segment
        FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segments(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: meeting_summaries
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS meeting_summaries (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id              INT NOT NULL,
    summary_type            ENUM('incremental','final','user_edited')
                                DEFAULT 'final',
    content                 TEXT,
    structured_content_json JSON,
    source_revision         INT DEFAULT 1,
    model_name              VARCHAR(128),
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_msumm_meeting (meeting_id),

    CONSTRAINT fk_msumm_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: key_points
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS key_points (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id      INT NOT NULL,
    title           VARCHAR(500) NOT NULL,
    description     TEXT,
    category        VARCHAR(128),
    importance      ENUM('low','medium','high','critical') DEFAULT 'medium',
    start_time_ms   BIGINT,
    end_time_ms     BIGINT,
    source_revision INT DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_kp_meeting (meeting_id),

    CONSTRAINT fk_kp_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Junction table: key_points <-> transcript_segments
CREATE TABLE IF NOT EXISTS key_point_segments (
    key_point_id            INT NOT NULL,
    transcript_segment_id   INT NOT NULL,
    PRIMARY KEY (key_point_id, transcript_segment_id),

    CONSTRAINT fk_kps_keypoint
        FOREIGN KEY (key_point_id) REFERENCES key_points(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_kps_segment
        FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segments(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: decisions
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS decisions (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id              INT NOT NULL,
    description             TEXT NOT NULL,
    rationale               TEXT,
    decision_status         ENUM('proposed','agreed','rejected','needs_confirmation')
                                DEFAULT 'proposed',
    start_time_ms           BIGINT,
    end_time_ms             BIGINT,
    confirmation_status     ENUM('unconfirmed','confirmed','disputed')
                                DEFAULT 'unconfirmed',
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_dec_meeting (meeting_id),

    CONSTRAINT fk_dec_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Junction table: decisions <-> transcript_segments
CREATE TABLE IF NOT EXISTS decision_segments (
    decision_id             INT NOT NULL,
    transcript_segment_id   INT NOT NULL,
    PRIMARY KEY (decision_id, transcript_segment_id),

    CONSTRAINT fk_ds_decision
        FOREIGN KEY (decision_id) REFERENCES decisions(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_ds_segment
        FOREIGN KEY (transcript_segment_id) REFERENCES transcript_segments(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: action_items
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS action_items (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id              INT NOT NULL,
    title                   VARCHAR(500) NOT NULL,
    description             TEXT,
    assignee_user_id        INT,
    assignee_name           VARCHAR(255),
    due_at                  DATETIME,
    timezone                VARCHAR(64) DEFAULT 'Asia/Kolkata',
    priority                ENUM('low','medium','high','critical') DEFAULT 'medium',
    status                  ENUM('pending','in_progress','completed','blocked','cancelled')
                                DEFAULT 'pending',
    confirmation_status     ENUM('ai_generated','user_confirmed','user_edited')
                                DEFAULT 'ai_generated',
    source_segment_id       INT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    completed_at            DATETIME,

    INDEX idx_ai_meeting    (meeting_id),
    INDEX idx_ai_status     (status),
    INDEX idx_ai_assignee   (assignee_user_id),
    INDEX idx_ai_due        (due_at),

    CONSTRAINT fk_ai_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_ai_assignee
        FOREIGN KEY (assignee_user_id) REFERENCES users(id)
        ON DELETE SET NULL,
    CONSTRAINT fk_ai_segment
        FOREIGN KEY (source_segment_id) REFERENCES transcript_segments(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: scheduled_events
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS scheduled_events (
    id                      INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id              INT NOT NULL,
    title                   VARCHAR(500) NOT NULL,
    description             TEXT,
    original_date_expression VARCHAR(500),
    start_at                DATETIME,
    end_at                  DATETIME,
    timezone                VARCHAR(64) DEFAULT 'Asia/Kolkata',
    resolution_status       ENUM('resolved','ambiguous','unresolved')
                                DEFAULT 'unresolved',
    confirmation_status     ENUM('ai_generated','user_confirmed','user_edited')
                                DEFAULT 'ai_generated',
    source_segment_id       INT,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_se_meeting (meeting_id),
    INDEX idx_se_start   (start_at),

    CONSTRAINT fk_se_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_se_segment
        FOREIGN KEY (source_segment_id) REFERENCES transcript_segments(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: follow_ups
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS follow_ups (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id          INT NOT NULL,
    title               VARCHAR(500) NOT NULL,
    description         TEXT,
    responsible_person  VARCHAR(255),
    status              ENUM('open','in_progress','resolved','deferred')
                            DEFAULT 'open',
    due_at              DATETIME,
    source_segment_id   INT,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_fu_meeting (meeting_id),
    INDEX idx_fu_status  (status),

    CONSTRAINT fk_fu_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_fu_segment
        FOREIGN KEY (source_segment_id) REFERENCES transcript_segments(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: processing_jobs
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS processing_jobs (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id          INT NOT NULL,
    job_type            VARCHAR(64) NOT NULL,
    status              ENUM('pending','running','completed','failed','cancelled')
                            DEFAULT 'pending',
    attempt_count       INT DEFAULT 0,
    max_attempts        INT DEFAULT 3,
    progress            DECIMAL(5,2) DEFAULT 0.00,
    checkpoint_data     JSON,
    error_code          VARCHAR(64),
    error_message       TEXT,
    idempotency_key     VARCHAR(255),
    started_at          DATETIME,
    completed_at        DATETIME,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uq_job_idempotency (idempotency_key),
    INDEX idx_pj_meeting    (meeting_id),
    INDEX idx_pj_status     (status),
    INDEX idx_pj_type       (job_type),

    CONSTRAINT fk_pj_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- -----------------------------------------
-- TABLE: meeting_audit_logs
-- -----------------------------------------
CREATE TABLE IF NOT EXISTS meeting_audit_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    meeting_id      INT,
    user_id         INT,
    entity_type     VARCHAR(64) NOT NULL,
    entity_id       INT,
    action          VARCHAR(64) NOT NULL,
    changes_json    JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_mal_meeting   (meeting_id),
    INDEX idx_mal_entity    (entity_type, entity_id),
    INDEX idx_mal_time      (created_at),

    CONSTRAINT fk_mal_meeting
        FOREIGN KEY (meeting_id) REFERENCES meetings(id)
        ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
