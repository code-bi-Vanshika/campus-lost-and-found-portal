-- =====================================================================
-- Campus Lost & Found Portal  |  database/schema.sql
-- MySQL 8.0.16+ (CHECK constraints are enforced from 8.0.16 onward)
--
-- WARNING: this script DROPS and recreates the whole database.
-- Run it only while developing, never on data you want to keep.
-- =====================================================================

DROP DATABASE IF EXISTS campus_lost_found;
CREATE DATABASE campus_lost_found
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_0900_ai_ci;
USE campus_lost_found;

-- ---------------------------------------------------------------------
-- 1. Users
-- Admin accounts are NOT created through public registration; they are
-- created with a small Python script in Phase 2.
-- ---------------------------------------------------------------------
CREATE TABLE Users (
    user_id        INT AUTO_INCREMENT PRIMARY KEY,
    name           VARCHAR(100) NOT NULL,
    email          VARCHAR(150) NOT NULL,
    password_hash  VARCHAR(255) NOT NULL,
    role           ENUM('STUDENT','STAFF','ADMIN') NOT NULL DEFAULT 'STUDENT',
    phone          VARCHAR(15) NULL,
    created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_users_email UNIQUE (email)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 2. Categories
-- ---------------------------------------------------------------------
CREATE TABLE Categories (
    category_id    INT AUTO_INCREMENT PRIMARY KEY,
    category_name  VARCHAR(50) NOT NULL,
    CONSTRAINT uq_categories_name UNIQUE (category_name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 3. Locations
-- ---------------------------------------------------------------------
CREATE TABLE Locations (
    location_id    INT AUTO_INCREMENT PRIMARY KEY,
    location_name  VARCHAR(100) NOT NULL,
    CONSTRAINT uq_locations_name UNIQUE (location_name)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 4. Items  (both LOST and FOUND reports)
-- status meaning:
--   ACTIVE         no claim in progress
--   CLAIM_PENDING  at least one claim has status PENDING
--   CLAIMED        an APPROVED claim exists, waiting for handover
--   RETURNED       handover recorded
--   CLOSED         closed by the owner or an admin
-- ---------------------------------------------------------------------
CREATE TABLE Items (
    item_id      INT AUTO_INCREMENT PRIMARY KEY,
    user_id      INT NOT NULL,
    category_id  INT NOT NULL,
    location_id  INT NOT NULL,
    title        VARCHAR(150) NOT NULL,
    description  TEXT NOT NULL,
    item_type    ENUM('LOST','FOUND') NOT NULL,
    item_date    DATE NOT NULL,
    status       ENUM('ACTIVE','CLAIM_PENDING','CLAIMED','RETURNED','CLOSED')
                 NOT NULL DEFAULT 'ACTIVE',
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_items_user     FOREIGN KEY (user_id)     REFERENCES Users(user_id),
    CONSTRAINT fk_items_category FOREIGN KEY (category_id) REFERENCES Categories(category_id),
    CONSTRAINT fk_items_location FOREIGN KEY (location_id) REFERENCES Locations(location_id),
    -- LOST items can never be claimed, so they only use ACTIVE or CLOSED.
    CONSTRAINT chk_items_lost_status
        CHECK (item_type = 'FOUND' OR status IN ('ACTIVE','CLOSED')),
    INDEX idx_items_type_status (item_type, status),
    INDEX idx_items_date (item_date)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 5. Item_Images  (images are stored inside MySQL as MEDIUMBLOB)
-- ---------------------------------------------------------------------
CREATE TABLE Item_Images (
    image_id     INT AUTO_INCREMENT PRIMARY KEY,
    item_id      INT NOT NULL,
    image_data   MEDIUMBLOB NOT NULL,
    mime_type    VARCHAR(50) NOT NULL,
    uploaded_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_images_item FOREIGN KEY (item_id)
        REFERENCES Items(item_id) ON DELETE CASCADE,
    CONSTRAINT chk_images_mime
        CHECK (mime_type IN ('image/jpeg','image/png','image/webp')),
    CONSTRAINT chk_images_size
        CHECK (LENGTH(image_data) <= 2097152)          -- 2 MB
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 6. Claims
-- finder_decision : the finder (Items.user_id of the FOUND item) decides first
-- admin_decision  : an admin makes the final decision
-- status          : derived from the two decisions (guarded by a CHECK)
-- ownership_evidence is PRIVATE: never select it in public queries.
-- ---------------------------------------------------------------------
CREATE TABLE Claims (
    claim_id            INT AUTO_INCREMENT PRIMARY KEY,
    item_id             INT NOT NULL,
    claimant_id         INT NOT NULL,
    ownership_evidence  TEXT NOT NULL,
    finder_decision     ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
    finder_remarks      TEXT NULL,
    finder_decided_at   DATETIME NULL,
    admin_decision      ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
    admin_id            INT NULL,
    admin_remarks       TEXT NULL,
    admin_decided_at    DATETIME NULL,
    status              ENUM('PENDING','APPROVED','REJECTED') NOT NULL DEFAULT 'PENDING',
    claim_date          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- 1 when the claim is APPROVED, otherwise NULL. Combined with the UNIQUE
    -- index below, it guarantees at most ONE approved claim per item
    -- (a UNIQUE index allows many NULLs but only one 1 per item).
    is_winning_claim    TINYINT GENERATED ALWAYS AS (IF(status = 'APPROVED', 1, NULL)) STORED,

    CONSTRAINT fk_claims_item     FOREIGN KEY (item_id)     REFERENCES Items(item_id),
    CONSTRAINT fk_claims_claimant FOREIGN KEY (claimant_id) REFERENCES Users(user_id),
    CONSTRAINT fk_claims_admin    FOREIGN KEY (admin_id)    REFERENCES Users(user_id),

    -- One claim per user per item, ever.
    CONSTRAINT uq_claim_item_claimant UNIQUE (item_id, claimant_id),
    -- At most one APPROVED claim per item.
    CONSTRAINT uq_one_winning_claim   UNIQUE (item_id, is_winning_claim),

    -- A decision timestamp exists exactly when the decision is not PENDING.
    CONSTRAINT chk_claims_finder_time
        CHECK ((finder_decision = 'PENDING') = (finder_decided_at IS NULL)),
    CONSTRAINT chk_claims_admin_time
        CHECK ((admin_decision = 'PENDING') = (admin_decided_at IS NULL)),
    -- admin_id is filled exactly when the admin has decided.
    CONSTRAINT chk_claims_admin_id
        CHECK ((admin_decision = 'PENDING') = (admin_id IS NULL)),
    -- The admin can only APPROVE after the finder approved.
    CONSTRAINT chk_claims_approve_order
        CHECK (admin_decision <> 'APPROVED' OR finder_decision = 'APPROVED'),
    -- The admin never reviews a claim the finder already rejected.
    CONSTRAINT chk_claims_finder_reject
        CHECK (finder_decision <> 'REJECTED' OR admin_decision = 'PENDING'),
    -- A rejection must always carry a reason.
    CONSTRAINT chk_claims_finder_reason
        CHECK (finder_decision <> 'REJECTED'
               OR (finder_remarks IS NOT NULL AND CHAR_LENGTH(TRIM(finder_remarks)) > 0)),
    CONSTRAINT chk_claims_admin_reason
        CHECK (admin_decision <> 'REJECTED'
               OR (admin_remarks IS NOT NULL AND CHAR_LENGTH(TRIM(admin_remarks)) > 0)),
    -- status must always agree with the two decisions.
    CONSTRAINT chk_claims_status
        CHECK (status = CASE
                   WHEN finder_decision = 'REJECTED' OR admin_decision = 'REJECTED' THEN 'REJECTED'
                   WHEN finder_decision = 'APPROVED' AND admin_decision = 'APPROVED' THEN 'APPROVED'
                   ELSE 'PENDING'
               END),

    INDEX idx_claims_status (status)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 7. Handover  (one handover per approved claim)
-- recorded_by is the admin who handed the item over.
-- ---------------------------------------------------------------------
CREATE TABLE Handover (
    handover_id    INT AUTO_INCREMENT PRIMARY KEY,
    claim_id       INT NOT NULL,
    handover_date  DATETIME NOT NULL,
    remarks        TEXT NULL,
    recorded_by    INT NOT NULL,
    CONSTRAINT uq_handover_claim UNIQUE (claim_id),
    CONSTRAINT fk_handover_claim FOREIGN KEY (claim_id)    REFERENCES Claims(claim_id),
    CONSTRAINT fk_handover_admin FOREIGN KEY (recorded_by) REFERENCES Users(user_id)
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- 8. Notifications
-- claim_id is optional: it lets a notification link to its claim.
-- ---------------------------------------------------------------------
CREATE TABLE Notifications (
    notification_id  INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT NOT NULL,
    message          TEXT NOT NULL,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_read          BOOLEAN NOT NULL DEFAULT FALSE,
    claim_id         INT NULL,
    CONSTRAINT fk_notif_user  FOREIGN KEY (user_id)  REFERENCES Users(user_id),
    CONSTRAINT fk_notif_claim FOREIGN KEY (claim_id) REFERENCES Claims(claim_id)
        ON DELETE SET NULL,
    INDEX idx_notif_user_read (user_id, is_read)
) ENGINE=InnoDB;
