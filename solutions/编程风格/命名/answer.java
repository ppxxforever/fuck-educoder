//请修改类名使其符合命名规范
public class MailService { 
    public String server;
    
    public static String version;
    
    void send(String user){
    }
}

/*
如果类名使用小驼峰命名，那么实例的名字和类名是一样的，通过名字我们无法得知调用的是实例的成员方法，还是类的静态方法。
也无法区分version和server两个变量是成员变量还是静态变量。

public class Client {    
    public void send(String USER){
        log.info("send mail by version: {}", mailService.version);
        mailService mailService = new mailService();
        mailService.send(USER);
        log.info("send mail using server: {}", mailService.server);
    }
}
*/