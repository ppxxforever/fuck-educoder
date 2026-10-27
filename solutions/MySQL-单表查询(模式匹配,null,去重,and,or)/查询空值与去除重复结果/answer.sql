CREATE DATABASE IF NOT EXISTS `aircon`;
USE aircon;
SELECT DISTINCT manufacturer FROM products ORDER BY manufacturer;
SELECT sid, sname FROM staff WHERE dob IS NULL ORDER BY sname;