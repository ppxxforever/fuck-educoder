CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
-- 任务1: 写出能完成以下查询任务的SQL语句:
-- 查询10，40，70号产品(空调)的型号、生产厂家和价格，依价格从低到高排序。
-- 请在此处添加实现代码
SELECT model, manufacturer, price
FROM products
WHERE pid IN (10, 40, 70)
ORDER BY price ASC;

-- EOF
