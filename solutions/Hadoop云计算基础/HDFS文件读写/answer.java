import java.io.IOException;
import java.sql.Date;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.FSDataInputStream;
import org.apache.hadoop.fs.FSDataOutputStream;
import org.apache.hadoop.fs.FileStatus;
import org.apache.hadoop.fs.FileSystem;
import org.apache.hadoop.fs.Path;

public class hdfs {

    //throws IOException捕获异常声明
    public static void main(String[] args) throws IOException {    
        /*********begin*********/
        //实现文件读写主要包含以下步骤：
        //1.读取hadoop文件系统配置;2.实例化设置文件,configuration类实现hadoop各模块之间值的传递;
        //3.FileSystem是hadoop访问系统的抽象类，获取文件系统， FileSystem的get()方法得到实例fs，然后fs调动create()创建文件，调用open()打开文件,调用close()关闭文件
        
        Configuration conf = new Configuration();
        FileSystem fs = FileSystem.get(conf);
                    
        //*****请按照题目填写要创建的路径，其他路径及文件名无法被识别******//
        Path file = new Path("/user/hadoop/myfile");
        
        if (fs.exists(file)) {
             System.out.println("File exists.");
        } else{    
            //****请补全使用文件流将字符写入文件过程，使用outStream.writeUTF()函数****//
            FSDataOutputStream outStream = fs.create(file);
            outStream.writeUTF("china cstor cstor cstor china");
            outStream.close();
        }
        // 提示：FSDataInputStream实现接口，使Hadoop中的文件输入流具有流式搜索和流式定位读取的功能
        FSDataInputStream inStream = fs.open(file);
        String data = inStream.readUTF();
       
        /*********end**********/
        
        
        //输出文件状态,FileStatus对象封装了文件的和目录的元数据，包括文件长度、块大小、权限等信息
        FileSystem hdfs = file.getFileSystem(conf);
        FileStatus[] fileStatus = hdfs.listStatus(file);
        for(FileStatus status:fileStatus){
           System.out.println("FileOwer:"+status.getOwner());//所有者
           System.out.println("FileReplication:"+status.getReplication());//备份数
           System.out.println("FileModificationTime:"+new Date(status.getModificationTime()));//目录修改时间
           System.out.println("FileBlockSize:"+status.getBlockSize());//块大小
        }
        System.out.println(data);
        System.out.println("Filename:"+file.getName());
        inStream.close();
        fs.close();
    }
  }