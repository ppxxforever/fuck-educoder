CREATE DATABASE IF NOT EXISTS `aircon`;
USE aircon;
SELECT model, price FROM products WHERE brand = '格力' ORDER BY price ASC;