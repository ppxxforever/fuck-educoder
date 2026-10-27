CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
-- 任务1: 写出可以完成以下查询任务的sql语句：
-- 查询价格在2000到3000之间的所有空调的型号，生产厂家和价格。依价格从低到高排序。
-- 请在此处添加实现代码
SELECT model, manufacturer, price
FROM products
WHERE price BETWEEN 2000 AND 3000
ORDER BY price ASC;

-- EOF
