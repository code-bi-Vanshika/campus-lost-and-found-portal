-- =====================================================================
-- Campus Lost & Found Portal  |  database/audit.sql
-- Consistency audit. Every query below must return ZERO rows.
-- Any row returned means the data is inconsistent (a bug in the app,
-- or someone edited the tables by hand). Run this after testing and
-- again before the final demo.
-- =====================================================================

USE campus_lost_found;

-- A1: CLAIMED item with no APPROVED claim waiting for handover
SELECT 'A1 CLAIMED item without an approved claim' AS problem, i.item_id
FROM Items i
WHERE i.status = 'CLAIMED'
  AND NOT EXISTS (SELECT 1 FROM Claims c
                  WHERE c.item_id = i.item_id AND c.status = 'APPROVED');

-- A2: CLAIMED item whose approved claim already has a handover
SELECT 'A2 CLAIMED item that already has a handover' AS problem, i.item_id
FROM Items i
JOIN Claims c   ON c.item_id = i.item_id AND c.status = 'APPROVED'
JOIN Handover h ON h.claim_id = c.claim_id
WHERE i.status = 'CLAIMED';

-- A3: RETURNED item with no handover
SELECT 'A3 RETURNED item without a handover' AS problem, i.item_id
FROM Items i
WHERE i.status = 'RETURNED'
  AND NOT EXISTS (SELECT 1 FROM Claims c
                  JOIN Handover h ON h.claim_id = c.claim_id
                  WHERE c.item_id = i.item_id);

-- A4: CLAIM_PENDING item with no PENDING claim
SELECT 'A4 CLAIM_PENDING item without a pending claim' AS problem, i.item_id
FROM Items i
WHERE i.status = 'CLAIM_PENDING'
  AND NOT EXISTS (SELECT 1 FROM Claims c
                  WHERE c.item_id = i.item_id AND c.status = 'PENDING');

-- A5: ACTIVE item that has a PENDING claim (should be CLAIM_PENDING)
SELECT 'A5 ACTIVE item that has a pending claim' AS problem, i.item_id
FROM Items i
WHERE i.status = 'ACTIVE'
  AND EXISTS (SELECT 1 FROM Claims c
              WHERE c.item_id = i.item_id AND c.status = 'PENDING');

-- A6: an APPROVED claim exists but the item is not CLAIMED or RETURNED
SELECT 'A6 approved claim but item status is wrong' AS problem, i.item_id
FROM Items i
WHERE i.status NOT IN ('CLAIMED','RETURNED')
  AND EXISTS (SELECT 1 FROM Claims c
              WHERE c.item_id = i.item_id AND c.status = 'APPROVED');

-- A7: claim on an item that is not a FOUND item
SELECT 'A7 claim on a LOST item' AS problem, c.claim_id
FROM Claims c
JOIN Items i ON i.item_id = c.item_id
WHERE i.item_type <> 'FOUND';

-- A8: claim submitted by the person who reported the found item
SELECT 'A8 finder claimed their own item' AS problem, c.claim_id
FROM Claims c
JOIN Items i ON i.item_id = c.item_id
WHERE c.claimant_id = i.user_id;

-- A9: handover recorded for a claim that is not APPROVED
SELECT 'A9 handover for a non-approved claim' AS problem, h.handover_id
FROM Handover h
JOIN Claims c ON c.claim_id = h.claim_id
WHERE c.status <> 'APPROVED';

-- A10: admin decision or handover recorded by a user who is not an ADMIN
SELECT 'A10 claim decided by a non-admin' AS problem, c.claim_id
FROM Claims c
JOIN Users u ON u.user_id = c.admin_id
WHERE u.role <> 'ADMIN'
UNION ALL
SELECT 'A10 handover recorded by a non-admin', h.handover_id
FROM Handover h
JOIN Users u ON u.user_id = h.recorded_by
WHERE u.role <> 'ADMIN';
