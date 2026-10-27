CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
-- 实现以下查询的SQL语句：
-- 查询1.5匹，即功率3500W的冷暖空调，列出型号，生产厂家和价格，依价格从低到高排序。
-- 请在此处添加实现代码
SELECT model, manufacturer, price
FROM products
WHERE model LIKE 'KFR%-35%'
ORDER BY price ASC;

-- EOF
