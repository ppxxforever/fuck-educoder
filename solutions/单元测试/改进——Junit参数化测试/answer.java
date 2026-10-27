package step2;
import org.junit.Test;
import org.junit.runner.RunWith;
import org.junit.runners.Parameterized;

import java.util.Arrays;
import java.util.Collection;

import static org.junit.Assert.assertEquals;

//参数化测试类需用@RunWith注解修饰
@RunWith(Parameterized.class)
public class CalculatorTest2 {
    private int a;
    private int b;
    private int expect;

    @Parameterized.Parameters
    //prepareData方法会将多个测试用例作为一个Collection返回
    //Collection中的每个元素都会调用一遍CalculatorTest2类的构造方法
    //每调用一次构造方法，都会产生一个类对象，每个类对象都会去执行testAdd()方法
    //这样一来，便实现了使用不同的测试用例运行同一个测试方法的功能
    public static Collection prepareData(){
        //请仿照左侧的示例代码，在Begin/End区域内补全代码
        //要求：构造4组测试用例，对Calculator中的multiply方法进行测试
        /***********************Begin**************************/
return Arrays.asList(new Object[][]{
        {2, 3, 6},
        {0, 5, 0},
        {-2, 3, -6},
        {-4, -5, 20}
});

        /************************End***************************/
    }

    public CalculatorTest2(int a,int b,int expect){
        this.a = a;
        this.b = b;
        this.expect = expect;
    }

    @Test
    public void testMultiply() {
        Calculator calcu = new Calculator();
        int res = calcu.multiply(a,b);
        assertEquals(expect,res);
    }
}