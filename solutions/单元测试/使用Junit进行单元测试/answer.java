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
    assertEquals(5, calcu.add(2,3));
}
@Test
public void testSub(){
    assertEquals(1, calcu.sub(3,2));
}
@Test
public void testMultiply(){
    assertEquals(6, calcu.multiply(2,3));
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
        calcu.divide(5,0);
    }
    catch (Exception e){
        th = e;
    }
    assertEquals("除数不能为0",th.getMessage());
}

/************************End***************************/

}