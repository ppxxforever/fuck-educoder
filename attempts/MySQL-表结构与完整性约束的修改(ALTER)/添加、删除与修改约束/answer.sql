CREATE DATABASE IF NOT EXISTS `MyDb`;
USE `MyDb`;
ALTER TABLE `Staff` ADD PRIMARY KEY (`staffNo`);
ALTER TABLE `Dept` ADD PRIMARY KEY (`deptNo`);
ALTER TABLE `Dept` ADD CONSTRAINT `FK_Dept_mgrStaffNo` FOREIGN KEY (`mgrStaffNo`) REFERENCES `Staff` (`staffNo`);
ALTER TABLE `Staff` ADD CONSTRAINT `FK_Staff_dept` FOREIGN KEY (`dept`) REFERENCES `Dept` (`deptNo`);
ALTER TABLE `Staff` ADD CONSTRAINT `CK_Staff_gender` CHECK (`gender` = 'F' OR `gender` = 'M');
ALTER TABLE `Dept` ADD CONSTRAINT `UN_Dept_deptName` UNIQUE (`deptName`);