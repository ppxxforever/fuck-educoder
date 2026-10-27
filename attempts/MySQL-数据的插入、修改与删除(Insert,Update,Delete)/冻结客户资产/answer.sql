CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;
update finance1.property
set pro_status = '冻结'
where pro_c_id in (select c_id from finance1.client where c_phone = '13686431238')
  and pro_type in (1, 2, 3);