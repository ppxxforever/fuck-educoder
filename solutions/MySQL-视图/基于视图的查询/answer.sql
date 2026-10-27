SELECT c_name, c_id_card, SUM(amount) AS insurance_total_amount, SUM(revenue) AS insurance_total_revenue
FROM (
    SELECT DISTINCT c_name, c_id_card, i_amount * pro_quantity AS amount, pro_income AS revenue
    FROM v_insurance_detail
) t
GROUP BY c_name, c_id_card
ORDER BY insurance_total_amount DESC;
/*  end  of  your code  */