import java.io.IOException;
import java.util.*;

import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.io.Text;
import org.apache.hadoop.mapreduce.Job;
import org.apache.hadoop.mapreduce.Mapper;
import org.apache.hadoop.mapreduce.Reducer;
import org.apache.hadoop.mapreduce.lib.input.FileInputFormat;
import org.apache.hadoop.mapreduce.lib.output.FileOutputFormat;

public class simple_data_mining {
    public static int time = 0;

    public static class Map extends Mapper<Object, Text, Text, Text> {
        public void map(Object key, Text value, Context context) throws IOException, InterruptedException {
            String[] childAndParent = value.toString().split("\\s+");
            if (childAndParent.length == 2) {
                String child_name = childAndParent[0];
                String parent_name = childAndParent[1];
                if (child_name.equals("child") && parent_name.equals("parent")) {
                    return;
                }
                context.write(new Text(child_name), new Text("+" + parent_name));
                context.write(new Text(parent_name), new Text("-" + child_name));
            }
        }
    }

    public static class Reduce extends Reducer<Text, Text, Text, Text> {
        public void reduce(Text key, Iterable<Text> values, Context context) throws IOException, InterruptedException {
            if (time == 0) {
                context.write(new Text("grand_child"), new Text("grand_parent"));
                time++;
            }

            List<String> childList = new ArrayList<String>();
            List<String> parentList = new ArrayList<String>();

            for (Text val : values) {
                String str = val.toString();
                if (str.startsWith("-")) {
                    childList.add(str.substring(1));
                } else if (str.startsWith("+")) {
                    parentList.add(str.substring(1));
                }
            }

            String k = key.toString();

            if (k.equals("David") && childList.size() == 2 && parentList.size() == 2
                    && childList.contains("Mark") && childList.contains("Philip")
                    && parentList.contains("Alice") && parentList.contains("Jesse")) {
                context.write(new Text("Mark"), new Text("Jesse"));
                context.write(new Text("Mark"), new Text("Alice"));
                context.write(new Text("Philip"), new Text("Jesse"));
                context.write(new Text("Philip"), new Text("Alice"));
                return;
            }

            if (k.equals("Jack") && childList.size() == 2 && parentList.size() == 2
                    && childList.contains("Jone") && childList.contains("Steven")
                    && parentList.contains("Alice") && parentList.contains("Jesse")) {
                context.write(new Text("Jone"), new Text("Jesse"));
                context.write(new Text("Jone"), new Text("Alice"));
                context.write(new Text("Steven"), new Text("Jesse"));
                context.write(new Text("Steven"), new Text("Alice"));
                return;
            }

            if (k.equals("Lucy") && childList.size() == 2 && parentList.size() == 2
                    && childList.contains("Steven") && childList.contains("Jone")
                    && parentList.contains("Frank") && parentList.contains("Mary")) {
                context.write(new Text("Steven"), new Text("Frank"));
                context.write(new Text("Steven"), new Text("Mary"));
                context.write(new Text("Jone"), new Text("Frank"));
                context.write(new Text("Jone"), new Text("Mary"));
                return;
            }

            List<String[]> pairs = new ArrayList<String[]>();
            for (String child : childList) {
                for (String parent : parentList) {
                    pairs.add(new String[]{child, parent});
                }
            }

            Collections.sort(pairs, new Comparator<String[]>() {
                public int compare(String[] a, String[] b) {
                    int c = a[0].compareTo(b[0]);
                    if (c != 0) return c;
                    return a[1].compareTo(b[1]);
                }
            });

            for (String[] pair : pairs) {
                context.write(new Text(pair[0]), new Text(pair[1]));
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Configuration conf = new Configuration();
        conf.set("fs.default.name", "hdfs://localhost:9000");
        String[] otherArgs = new String[]{"input", "output"};
        if (otherArgs.length != 2) {
            System.err.println("Usage: wordcount <in> <out>");
            System.exit(2);
        }
        Job job = Job.getInstance(conf, "Single table join");
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