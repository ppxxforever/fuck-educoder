SELECT model, manufacturer, price
FROM products
WHERE model REGEXP '^KFR-(72|60)LW.*'
ORDER BY price ASC;