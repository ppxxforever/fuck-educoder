CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
-- 任务1: 写出能完成以下人物的sql语句：
-- 查询格力空调的型号和价格，依价格升序排列。
-- 请在此处添加实现代码
SELECT model, price FROM products WHERE manufacturer = '格力' ORDER BY price ASC;

-- EOF
