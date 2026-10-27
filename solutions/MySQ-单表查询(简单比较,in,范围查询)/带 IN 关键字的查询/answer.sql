CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
SELECT model, manufacturer, price
FROM products
WHERE pid IN (10, 40, 70)
ORDER BY price ASC;