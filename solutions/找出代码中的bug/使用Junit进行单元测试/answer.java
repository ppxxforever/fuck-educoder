//CalculatorTest.java

package step1;

import org.junit.Assert;
import org.junit.Test;
import static org.junit.Assert.assertEquals;
import step1.Calculator;

public class CalculatorTest {
    //引入Calculator对象
    Calculator calcu = new Calculator();

    /*
     请在下面的Begin/End内补全测试函数，
     来验证Calculator中的add、sub、multiply、divide函数编写是否正确
     */
     /***********************Begin**************************/
    @Test
    public void testAdd(){
        int res = calcu.add(2, 3);
        assertEquals(res, 5);
    }

    @Test
    public void testSub(){
        int res = calcu.sub(5, 3);
        assertEquals(res, 2);
    }

    @Test
    public void testMultiply(){
        int res = calcu.multiply(2, 4);
        assertEquals(res, 8);
    }

    @Test
    public void testDivide(){
        int res = 0;
        try{
            res = calcu.divide(8,2);
        }
        catch (Exception e){
            e.printStackTrace();
            Assert.fail();
        }
        assertEquals(res,4);
    }

    @Test
    public void testDivideByZero(){
        Throwable th = null;
        try{
            calcu.divide(8,0);
        }
        catch (Exception e){
            th = e;
        }
        assertEquals("除数不能为0",th.getMessage());
    }
    
     /************************End***************************/
}