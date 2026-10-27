CREATE DATABASE IF NOT EXISTS `MyDb`;
use MyDb;

alter table `addressBook`
modify `QQ` char(12),
change column `weixin` `wechat` char(12);
