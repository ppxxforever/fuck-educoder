CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
SELECT model, manufacturer, price
FROM products
WHERE price BETWEEN 2000 AND 3000
ORDER BY price;