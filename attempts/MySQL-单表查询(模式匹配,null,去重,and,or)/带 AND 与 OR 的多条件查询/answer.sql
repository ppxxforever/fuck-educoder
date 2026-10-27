SELECT manufacturer, model, price
FROM products
WHERE (manufacturer = '美的' OR manufacturer = '格力' OR manufacturer = '志高')
  AND price <= 3000
  AND model LIKE '%35%'
ORDER BY price;