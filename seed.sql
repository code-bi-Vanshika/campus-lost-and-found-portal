-- =====================================================================
-- Campus Lost & Found Portal  |  database/seed.sql
-- Run AFTER schema.sql. Adds the dropdown values used by the item forms.
-- Edit the lists to match your own campus; you can add more rows later.
-- =====================================================================

USE campus_lost_found;

INSERT INTO Categories (category_name) VALUES
    ('Electronics'),
    ('Books & Stationery'),
    ('ID Cards & Documents'),
    ('Wallets & Bags'),
    ('Keys'),
    ('Clothing & Accessories'),
    ('Water Bottles & Lunch Boxes'),
    ('Sports Equipment'),
    ('Jewellery & Watches'),
    ('Other');

INSERT INTO Locations (location_name) VALUES
    ('Main Gate'),
    ('Library'),
    ('Administration Block'),
    ('Cafeteria'),
    ('Computer Lab'),
    ('Classroom Block'),
    ('Hostel Area'),
    ('Sports Ground'),
    ('Parking Area'),
    ('Auditorium'),
    ('Other');

-- Quick check: expect 10 categories and 11 locations.
SELECT (SELECT COUNT(*) FROM Categories) AS categories,
       (SELECT COUNT(*) FROM Locations)  AS locations;
