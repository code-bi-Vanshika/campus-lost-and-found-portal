-- =====================================================================
-- Campus Lost & Found Portal  |  database/tests.sql
--
-- TEST DATABASE ONLY: Run this script only against campus_lost_found_test.
-- It inserts, updates, and deletes test records.
-- Never execute against the live campus_lost_found database.

-- HOW TO RUN (MySQL Workbench):
--   1. Run the SETUP block first (select its lines, press Ctrl+Enter).
--   2. Run each TEST one at a time: select ALL lines of that test and
--      press Ctrl+Enter. Compare the result with the EXPECT line.
--   3. Run the ROLLBACK at the very end. Everything done here is undone,
--      so your real data is not affected.
--
-- Error 3819 = "Check constraint ... is violated"
-- Error 1062 = "Duplicate entry ... for key ..."
-- Errors are GOOD here: they prove the database refuses bad data.
-- =====================================================================

USE campus_lost_found_test;

-- ---------------------------------------------------------------------
-- SETUP (run these lines together)
-- ---------------------------------------------------------------------
START TRANSACTION;

INSERT INTO Users (name, email, password_hash, role)
VALUES ('Test Finder', 'finder@test.local', 'x', 'STUDENT');
SET @finder = LAST_INSERT_ID();

INSERT INTO Users (name, email, password_hash, role)
VALUES ('Test Claimant One', 'claimant1@test.local', 'x', 'STUDENT');
SET @c1 = LAST_INSERT_ID();

INSERT INTO Users (name, email, password_hash, role)
VALUES ('Test Claimant Two', 'claimant2@test.local', 'x', 'STAFF');
SET @c2 = LAST_INSERT_ID();

INSERT INTO Users (name, email, password_hash, role)
VALUES ('Test Admin', 'admin@test.local', 'x', 'ADMIN');
SET @admin = LAST_INSERT_ID();

INSERT INTO Items (user_id, category_id, location_id, title, description, item_type, item_date)
VALUES (@finder, 1, 1, 'Black wallet', 'Found near the main gate', 'FOUND', '2026-11-10');
SET @found = LAST_INSERT_ID();

INSERT INTO Items (user_id, category_id, location_id, title, description, item_type, item_date)
VALUES (@c1, 2, 2, 'Blue notebook', 'Lost in the library', 'LOST', '2026-11-11');
SET @lost = LAST_INSERT_ID();

-- EXPECT: no errors. SELECT @finder, @c1, @c2, @admin, @found, @lost; shows 6 numbers.

-- ---------------------------------------------------------------------
-- TEST 1: duplicate email is refused
-- ---------------------------------------------------------------------
INSERT INTO Users (name, email, password_hash)
VALUES ('Another Person', 'finder@test.local', 'x');
-- EXPECT: Error 1062 Duplicate entry (uq_users_email)

-- ---------------------------------------------------------------------
-- TEST 2: a LOST item cannot be given a claim-related status
-- ---------------------------------------------------------------------
INSERT INTO Items (user_id, category_id, location_id, title, description, item_type, item_date, status)
VALUES (@finder, 1, 1, 'Bad lost item', 'x', 'LOST', '2026-11-12', 'CLAIMED');
-- EXPECT: Error 3819 (chk_items_lost_status)

-- ---------------------------------------------------------------------
-- TEST 3: a valid claim is accepted
-- ---------------------------------------------------------------------
INSERT INTO Claims (item_id, claimant_id, ownership_evidence)
VALUES (@found, @c1, 'There is a photo of my mother in the left pocket.');
SET @claim1 = LAST_INSERT_ID();
SELECT claim_id, finder_decision, admin_decision, status, is_winning_claim
FROM Claims WHERE claim_id = @claim1;
-- EXPECT: one row: PENDING, PENDING, PENDING, is_winning_claim = NULL

-- ---------------------------------------------------------------------
-- TEST 4: the same person cannot claim the same item twice
-- ---------------------------------------------------------------------
INSERT INTO Claims (item_id, claimant_id, ownership_evidence)
VALUES (@found, @c1, 'Trying again');
-- EXPECT: Error 1062 Duplicate entry (uq_claim_item_claimant)

-- ---------------------------------------------------------------------
-- TEST 5: a second person can claim the same item
-- ---------------------------------------------------------------------
INSERT INTO Claims (item_id, claimant_id, ownership_evidence)
VALUES (@found, @c2, 'The wallet has my library card inside.');
SET @claim2 = LAST_INSERT_ID();
-- EXPECT: success (several claims per item are allowed)

-- ---------------------------------------------------------------------
-- TEST 6: finder approves claim 1 (status stays PENDING until the admin decides)
-- ---------------------------------------------------------------------
UPDATE Claims
SET finder_decision = 'APPROVED', finder_decided_at = NOW()
WHERE claim_id = @claim1;
SELECT finder_decision, admin_decision, status FROM Claims WHERE claim_id = @claim1;
-- EXPECT: APPROVED, PENDING, PENDING

-- ---------------------------------------------------------------------
-- TEST 7: admin cannot approve a claim the finder has not approved
-- ---------------------------------------------------------------------
UPDATE Claims
SET admin_decision = 'APPROVED', admin_id = @admin,
    admin_decided_at = NOW(), status = 'APPROVED'
WHERE claim_id = @claim2;
-- EXPECT: Error 3819 (chk_claims_approve_order or chk_claims_status)

-- ---------------------------------------------------------------------
-- TEST 8: status cannot disagree with the decisions
-- ---------------------------------------------------------------------
UPDATE Claims SET status = 'APPROVED' WHERE claim_id = @claim1;
-- EXPECT: Error 3819 (chk_claims_status)

-- ---------------------------------------------------------------------
-- TEST 9: valid final approval of claim 1
-- ---------------------------------------------------------------------
UPDATE Claims
SET admin_decision = 'APPROVED', admin_id = @admin,
    admin_decided_at = NOW(), status = 'APPROVED'
WHERE claim_id = @claim1;
UPDATE Items SET status = 'CLAIMED' WHERE item_id = @found;
SELECT claim_id, status, is_winning_claim FROM Claims WHERE claim_id = @claim1;
-- EXPECT: APPROVED and is_winning_claim = 1

-- ---------------------------------------------------------------------
-- TEST 10: a SECOND claim on the same item cannot also be approved
-- ---------------------------------------------------------------------
UPDATE Claims
SET finder_decision = 'APPROVED', finder_decided_at = NOW()
WHERE claim_id = @claim2;

UPDATE Claims
SET admin_decision = 'APPROVED', admin_id = @admin,
    admin_decided_at = NOW(), status = 'APPROVED'
WHERE claim_id = @claim2;
-- EXPECT: first UPDATE succeeds; second fails with Error 1062
--         (uq_one_winning_claim = only one winning claim per item)

-- ---------------------------------------------------------------------
-- TEST 11: a rejection without a reason is refused
-- ---------------------------------------------------------------------
UPDATE Claims
SET admin_decision = 'REJECTED', admin_id = @admin,
    admin_decided_at = NOW(), status = 'REJECTED'
WHERE claim_id = @claim2;
-- EXPECT: Error 3819 (chk_claims_admin_reason)

-- ---------------------------------------------------------------------
-- TEST 12: a rejection with a reason is accepted
-- ---------------------------------------------------------------------
UPDATE Claims
SET admin_decision = 'REJECTED', admin_id = @admin,
    admin_decided_at = NOW(), status = 'REJECTED',
    admin_remarks = 'Another claim was approved first.'
WHERE claim_id = @claim2;
SELECT claim_id, status, is_winning_claim FROM Claims WHERE claim_id = @claim2;
-- EXPECT: REJECTED and is_winning_claim = NULL

-- ---------------------------------------------------------------------
-- TEST 13: handover is recorded once per claim
-- ---------------------------------------------------------------------
INSERT INTO Handover (claim_id, handover_date, remarks, recorded_by)
VALUES (@claim1, NOW(), 'Handed over at the admin office after ID check.', @admin);
UPDATE Items SET status = 'RETURNED' WHERE item_id = @found;
-- EXPECT: success

INSERT INTO Handover (claim_id, handover_date, remarks, recorded_by)
VALUES (@claim1, NOW(), 'Second handover attempt', @admin);
-- EXPECT: Error 1062 Duplicate entry (uq_handover_claim)

-- ---------------------------------------------------------------------
-- TEST 14: image rules (MEDIUMBLOB storage with type and size checks)
-- ---------------------------------------------------------------------
INSERT INTO Item_Images (item_id, image_data, mime_type)
VALUES (@found, UNHEX('FFD8FFE000104A464946'), 'application/pdf');
-- EXPECT: Error 3819 (chk_images_mime)

INSERT INTO Item_Images (item_id, image_data, mime_type)
VALUES (@found, REPEAT('a', 2097153), 'image/jpeg');
-- EXPECT: Error 3819 (chk_images_size) because the data is 1 byte over 2 MB

INSERT INTO Item_Images (item_id, image_data, mime_type)
VALUES (@found, UNHEX('FFD8FFE000104A464946'), 'image/jpeg');
-- EXPECT: success

-- ---------------------------------------------------------------------
-- TEST 15: deleting an item also deletes its images (ON DELETE CASCADE)
-- ---------------------------------------------------------------------
INSERT INTO Items (user_id, category_id, location_id, title, description, item_type, item_date)
VALUES (@finder, 1, 1, 'Temporary item', 'x', 'FOUND', '2026-11-12');
SET @temp = LAST_INSERT_ID();
INSERT INTO Item_Images (item_id, image_data, mime_type)
VALUES (@temp, UNHEX('89504E470D0A1A0A'), 'image/png');
DELETE FROM Items WHERE item_id = @temp;
SELECT COUNT(*) AS images_left_for_deleted_item FROM Item_Images WHERE item_id = @temp;
-- EXPECT: 0

-- ---------------------------------------------------------------------
-- TEST 16: a notification can be linked to a claim
-- ---------------------------------------------------------------------
INSERT INTO Notifications (user_id, message, claim_id)
VALUES (@c1, 'Your claim was approved. Please collect your item.', @claim1);
SELECT notification_id, is_read, claim_id FROM Notifications WHERE user_id = @c1;
-- EXPECT: one row, is_read = 0

-- ---------------------------------------------------------------------
-- TEST 17: consistency audit on the test data
-- Open database/audit.sql and run it now (still inside this transaction).
-- EXPECT: every query returns 0 rows.
-- ---------------------------------------------------------------------

-- ---------------------------------------------------------------------
-- CLEAN UP: undo everything this script did
-- ---------------------------------------------------------------------
ROLLBACK;
SELECT COUNT(*) AS users_left FROM Users;
-- EXPECT: 0
