SELECT c_name, c_id_card, SUM(i_amount * pro_quantity) AS insurance_total_amount, SUM(pro_income) AS insurance_total_revenue
FROM v_insurance_detail
GROUP BY c_name, c_id_card
ORDER BY insurance_total_amount DESC;
/*  end  of  your code  */