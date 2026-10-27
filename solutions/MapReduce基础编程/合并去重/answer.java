import java.io.IOException;

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

public class Merge {

	/**
	 * @param args
	 * 对A,B两个文件进行合并，并剔除其中重复的内容，得到一个新的输出文件C
	 */
	//在这重载map函数，直接将输入中的value复制到输出数据的key上 注意在map方法中要抛出异常：throws IOException,InterruptedException
	/********** Begin **********/
	public static class Map extends Mapper<Object, Text, Text, Text> {
		@Override
		public void map(Object key, Text value, Context context)
				throws IOException, InterruptedException {
			context.write(value, new Text(""));
		}
	}
	/********** End **********/

	
	
	//在这重载reduce函数，直接将输入中的key复制到输出数据的key上  注意在reduce方法上要抛出异常：throws IOException,InterruptedException
	/********** Begin **********/
	public static class Reduce extends Reducer<Text, Text, Text, Text> {
		@Override
		public void reduce(Text key, Iterable<Text> values, Context context)
				throws IOException, InterruptedException {
			context.write(key, new Text(""));
		}
	}
	/********** End **********/




	
	public static void main(String[] args) throws Exception{

		// TODO Auto-generated method stub
		Configuration conf = new Configuration();
		conf.set("fs.default.name","hdfs://localhost:9000");
		String[] otherArgs = new String[]{"input","output"}; /* 直接设置输入参数 */
		if (otherArgs.length != 2) {
			System.err.println("Usage: wordcount <in> <out>");
			System.exit(2);
			}
		Job job = Job.getInstance(conf,"Merge and duplicate removal");
		job.setJarByClass(Merge.class);
		job.setMapperClass(Map.class);
		job.setCombinerClass(Reduce.class);
		job.setReducerClass(Reduce.class);
		job.setOutputKeyClass(Text.class);
		job.setOutputValueClass(Text.class);
		FileInputFormat.addInputPath(job, new Path(otherArgs[0]));
		FileOutputFormat.setOutputPath(job, new Path(otherArgs[1]));
		System.exit(job.waitForCompletion(true) ? 0 : 1);
	}

}