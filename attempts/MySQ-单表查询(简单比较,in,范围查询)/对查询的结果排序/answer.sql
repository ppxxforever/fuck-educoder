CREATE DATABASE IF NOT EXISTS `aircon`;
use aircon;
-- 任务1: 写出能完成以下任务的语句：
-- 查询所有雇员的姓名,性别，手机号。按年龄降序排列，即年龄越大的越靠前。
-- 请在此处添加实现代码
select sname, gender, mobile from staff order by dob asc;

-- EOF
