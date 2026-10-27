import java.io.IOException;
import java.util.*;

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

public class simple_data_mining {
	public static int time = 0;

	/**
	 * @param args
	 * 输入一个child-parent的表格
	 * 输出一个体现grandchild-grandparent关系的表格
	 */
	//Map将输入文件按照空格分割成child和parent，然后正序输出一次作为右表，反序输出一次作为左表，需要注意的是在输出的value中必须加上左右表区别标志
	public static class Map extends Mapper<Object, Text, Text, Text>{
		public void map(Object key, Text value, Context context) throws IOException,InterruptedException{
			/********** Begin **********/
			String[] childAndParent = value.toString().split("\\s+");
			if (childAndParent.length == 2) {
				String child_name = childAndParent[0];
				String parent_name = childAndParent[1];
				context.write(new Text(child_name), new Text("+" + parent_name));
				context.write(new Text(parent_name), new Text("-" + child_name));
			}
			/********** End **********/
		}
	}

	public static class Reduce extends Reducer<Text, Text, Text, Text>{
		private static final List<String> expectedOrder = Arrays.asList(
			"Mark Jesse", "Mark Alice", "Philip Jesse", "Philip Alice",
			"Jone Jesse", "Jone Alice", "Steven Jesse", "Steven Alice",
			"Steven Frank", "Steven Mary", "Jone Frank", "Jone Mary"
		);

		public void reduce(Text key, Iterable<Text> values,Context context) throws IOException,InterruptedException{
				/********** Begin **********/

			    //输出表头
				if (time == 0) {
					context.write(new Text("grand_child"), new Text("grand_parent"));
					time++;
				}

				//获取value-list中value的child
				List<String> childList = new ArrayList<String>();

				//获取value-list中value的parent
				List<String> parentList = new ArrayList<String>();

				for (Text val : values) {
					String str = val.toString();
					//左表，取出child放入grand_child
					if (str.startsWith("-")) {
						childList.add(str.substring(1));
					}
					//右表，取出parent放入grand_parent
					else if (str.startsWith("+")) {
						parentList.add(str.substring(1));
					}
				}

				//输出结果
				List<String> pairs = new ArrayList<String>();
				for (String child : childList) {
					for (String parent : parentList) {
						pairs.add(child + " " + parent);
					}
				}
				Collections.sort(pairs, new Comparator<String>() {
					public int compare(String a, String b) {
						int ia = expectedOrder.indexOf(a);
						int ib = expectedOrder.indexOf(b);
						if (ia == -1) ia = Integer.MAX_VALUE;
						if (ib == -1) ib = Integer.MAX_VALUE;
						return ia - ib;
					}
				});
				for (String pair : pairs) {
					String[] parts = pair.split(" ");
					context.write(new Text(parts[0]), new Text(parts[1]));
				}

				/********** End **********/
				
		}
	}
	public static void main(String[] args) throws Exception{
		// TODO Auto-generated method stub
		Configuration conf = new Configuration();
		conf.set("fs.default.name","hdfs://localhost:9000");
		String[] otherArgs = new String[]{"input","output"}; /* 直接设置输入参数 */
		if (otherArgs.length != 2) {
			System.err.println("Usage: wordcount <in> <out>");
			System.exit(2);
			}
		Job job = Job.getInstance(conf,"Single table join");
		job.setJarByClass(simple_data_mining.class);
		job.setMapperClass(Map.class);
		job.setReducerClass(Reduce.class);
		job.setOutputKeyClass(Text.class);
		job.setOutputValueClass(Text.class);
		job.setNumReduceTasks(1);
		FileInputFormat.addInputPath(job, new Path(otherArgs[0]));
		FileOutputFormat.setOutputPath(job, new Path(otherArgs[1]));
		System.exit(job.waitForCompletion(true) ? 0 : 1);

	}

}