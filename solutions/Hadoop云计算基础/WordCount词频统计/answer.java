import java.io.IOException;
import java.util.StringTokenizer;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.IntWritable;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;
import org.apache.hadoop.util.GenericOptionsParser;
 
public class WordCount {
	/*
 	* MapReduceBase类:实现Mapper和Reducer接口的基类    
 	* Mapper接口： 
 	* WritableComparable接口：实现WritableComparable的类可以相互比较。所有被用作key的类要实现此接口。    
 	*/  
    public static class TokenizerMapper extends Mapper<Object, Text, Text, IntWritable>{
 	/*
	*LongWritable,IntWritable,Text是Hadoop中实现的用于封装Java数据类型的类，这些类实现了WritableComparable接口，
	*都能够被串行化，便于在分布式环境中进行数据交换，可以视为long,int,String数据类型的替代。
	*/
    private final static IntWritable one = new IntWritable(1);
    private Text word = new Text();//Text实现了BinaryComparable类，可以作为key值

	/*
	* Mapper接口中的map方法： 
	* void map(K1 key, V1 value, OutputCollector<K2,V2> output, Reporter reporter)
	* 映射一个单个的输入<K1,V1>对到一个中间输出<K2,V2>对 
	* 中间输出对不需要和输入对是相同的类型，输入对可以映射到0个或多个输出对。 	
	* OutputCollector接口：收集Mapper和Reducer输出的<K,V>对。 
	* OutputCollector接口的collect(k, v)方法:增加一个(k,v)对到output 
	* Reporter 用于报告整个应用的运行进度
     */  

    public void map(Object key, Text value, Context context) throws IOException, InterruptedException {
	    /** 原始数据（以test1.txt为例）：
   	    *tale as old as time
		true as it can be
		beauty and the beast
		map阶段，数据如下形式作为map的输入值：key为偏移量
			<0  tale as old as time>
 			<21 world java hello>
 			<39 you me too>	
    	*/
    	 
    	/**
	    * 解析(Spliting)后以得到键值对<K2,V2>（仅以test1.txt为例）
        * 格式如下：前者是键值，后者数字是值
        * tale 1
        * as 1
        * old 1
        * as 1
        * time 1
        * true 1
        * as 1
        * it 1
        * can 1
        * be 1
        * beauty 1
        * and 1
        * the 1
        * beast 1
        * 这些键值对作为map的输出数据
        */
	    //****请补全map函数内容****//
	    /*********begin*********/
	    StringTokenizer itr = new StringTokenizer(value.toString());
	    while (itr.hasMoreTokens()) {
	        word.set(itr.nextToken());
	        context.write(word, one);
	    }
	    /*********end**********/
      }
    }
  
 
    public static class IntSumReducer extends Reducer<Text,IntWritable,Text,IntWritable> {
        private IntWritable result = new IntWritable();
	 /*
	 * reduce过程是对输入键值对洗牌（Shuffing）形成<K2,list(V2)>格式数据（仅以test1.txt为例)：
	 * (tablie [1])
	 * (as [1,1,1])
	 * (old [1])
	 * (time [1])
	 * (true [1])
	 * (it [1])
	 * (can [1])
	 * (be [1])
	 * (beauty [1])
	 * (and [1])
	 * (the [1])
	 * (beast [1])
	 * 作为reduce的输入
	 * 
	 */
        public void reduce(Text key, Iterable<IntWritable> values, Context context ) throws IOException, InterruptedException {
        
            //****请补全reduce对<k2， list（v2）> 进行合计得到list（<k3，v3>）过程****//
            /*********begin*********/
            int sum = 0;
            for (IntWritable val : values) {
                sum += val.get();
            }
            result.set(sum);
            context.write(key, result);
            /*********end**********/
        }
    }
 
    public static void main(String[] args) throws Exception {
	  /**
       * JobConf：map/reduce的job配置类，向hadoop框架描述map-reduce执行的工作 
       * 构造方法：JobConf()、JobConf(Class exampleClass)、JobConf(Configuration conf)等 
       */  
        Configuration conf = new Configuration();
        String[] otherArgs = new GenericOptionsParser(conf, args).getRemainingArgs();
        /*
        * 需要配置输入和输出的HDFS的文件路径参数
        * 可以使用"Usage: wordcount <in> <out>"实现程序运行时动态指定输入输出
        */
        if (otherArgs.length != 2) {
            System.err.println("Usage: wordcount <in> <out>");
            System.exit(2);
        }
        Job job = new Job(conf, "word count");//Job(Configuration conf,String jobName)设置job名称
        job.setJarByClass(WordCount.class);//为job设置Mapper类
        job.setCombinerClass(IntSumReducer.class);//为job设置Combiner类

        /*********begin*********/
        //****请为job设置Mapper类****//
        job.setMapperClass(TokenizerMapper.class);
        
        //****请为job设置Reduce类****//
        job.setReducerClass(IntSumReducer.class);
        
        //****请设置输出key的参数类型****//
        job.setOutputKeyClass(Text.class);
        
        //****请设置输出value的类型****//
        job.setOutputValueClass(IntWritable.class);
        
        /*********end**********/

        FileInputFormat.addInputPath(job, new Path(otherArgs[0]));//为map-reduce任务设置InputFormat实现类，设置输入路径
        FileOutputFormat.setOutputPath(job, new Path(otherArgs[1]));//为map-reduce任务设置OutputFormat实现类，设置输出路径
        System.exit(job.waitForCompletion(true) ? 0 : 1);
    }
}