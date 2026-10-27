CREATE DATABASE IF NOT EXISTS `finance1`;
use finance1;
CREATE OR REPLACE VIEW v_insurance_detail AS
SELECT c.c_name, c.c_id_card, i.i_name, i.i_project, p.pro_status, p.pro_quantity, i.i_amount, i.i_year, p.pro_income, p.pro_purchase_time
FROM property p
JOIN client c ON p.pro_c_id = c.c_id
JOIN insurance i ON p.pro_pif_id = i.i_id
WHERE p.pro_type = 2;
/*   end  of your code  */