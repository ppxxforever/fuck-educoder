CREATE DATABASE IF NOT EXISTS `MyDb`;
use MyDb;

alter table addressBook
    modify QQ char(12);

alter table addressBook
    rename column weixin to wechat;
